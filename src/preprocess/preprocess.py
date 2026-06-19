import pandas as pd
import numpy as np
import os
import itertools

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.join(SCRIPT_DIR, "..", "..")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "outputs", "csv")
os.makedirs(OUTPUT_DIR, exist_ok=True)

print("1. 데이터 로드 중...")
data = pd.read_csv(os.path.join(PROJECT_ROOT, "data", "arxiv_trends.csv"))
df = pd.DataFrame(data)

df_drop = df.drop(['Datestamp', 'SetSpecs', 'ID', 'Abstract'], axis=1)
df_replace = df_drop[['Identifier', 'DOI', 'CitationCount', 'Created', 'Updated', 'Category', 'Title']]

print("2. 시계열 데이터 구성을 위한 전처리 중...")
df_exploded = df_replace.copy()
df_exploded['Category'] = df_exploded['Category'].astype(str).str.split(' ')
df_exploded = df_exploded.explode('Category')
df_exploded['Date'] = pd.to_datetime(df_exploded['Created'], errors='coerce').dt.date

df_exploded = df_exploded.dropna(subset=['Date'])
daily_counts = df_exploded.groupby(['Date', 'Category']).size().reset_index(name='Count')
daily_counts['Date'] = pd.to_datetime(daily_counts['Date'])

pivot_counts = daily_counts.pivot(index='Date', columns='Category', values='Count')
min_date = pivot_counts.index.min()
max_date = pivot_counts.index.max()
all_dates = pd.date_range(min_date, max_date, freq='D')
pivot_counts = pivot_counts.reindex(all_dates, fill_value=0).fillna(0)

print("3. 카테고리 간 공분산 및 유사도(피어슨 상관계수) 계산 중...")
cov_matrix = pivot_counts.cov()
corr_matrix = pivot_counts.corr()

cov_matrix.to_csv(os.path.join(OUTPUT_DIR, 'category_covariance.csv'), encoding='utf-8-sig')
corr_matrix.to_csv(os.path.join(OUTPUT_DIR, 'category_similarity.csv'), encoding='utf-8-sig')

print("4. 7일 이동평균, 속도(1차 미분), 가속도(2차 미분) 계산 중...")
ma_7d = pivot_counts.rolling(window=7, min_periods=1).mean()
trend_speed = ma_7d.diff(periods=1).fillna(0)
trend_accel = trend_speed.diff(periods=1).fillna(0)

ma_7d_long = ma_7d.reset_index().melt(id_vars='index', var_name='Category', value_name='MA_7D')
trend_speed_long = trend_speed.reset_index().melt(id_vars='index', var_name='Category', value_name='Trend_Speed')
trend_accel_long = trend_accel.reset_index().melt(id_vars='index', var_name='Category', value_name='Trend_Acceleration')

for df_long in [ma_7d_long, trend_speed_long, trend_accel_long]:
    df_long.rename(columns={'index': 'Date'}, inplace=True)

time_series_features = pd.merge(ma_7d_long, trend_speed_long, on=['Date', 'Category'])
time_series_features = pd.merge(time_series_features, trend_accel_long, on=['Date', 'Category'])
time_series_features.to_csv(os.path.join(OUTPUT_DIR, 'category_trend_features.csv'), index=False, encoding='utf-8-sig')

print("5. 원본 데이터에 파생 변수(새 성분) 병합 중...")
df_replace['Date'] = pd.to_datetime(df_replace['Created'], errors='coerce')

df_merge_base = df_replace[['Identifier', 'Date', 'Category']].copy()
df_merge_base['Category_Split'] = df_merge_base['Category'].astype(str).str.split(' ')
df_exploded_merge = df_merge_base.explode('Category_Split')

merged_trends = pd.merge(df_exploded_merge, time_series_features, 
                         left_on=['Date', 'Category_Split'], 
                         right_on=['Date', 'Category'], 
                         how='left')

trend_agg = merged_trends.groupby('Identifier')[['MA_7D', 'Trend_Speed', 'Trend_Acceleration']].mean().reset_index()
trend_agg.rename(columns={
    'MA_7D': 'Avg_MA_7D', 
    'Trend_Speed': 'Avg_Trend_Speed', 
    'Trend_Acceleration': 'Avg_Trend_Acceleration'
}, inplace=True)

def calc_sim_cov(cats_str):
    cats = str(cats_str).split(' ')
    if len(cats) > 1:
        pairs = list(itertools.combinations(cats, 2))
        sim_scores = [corr_matrix.loc[c1, c2] for c1, c2 in pairs if c1 in corr_matrix.columns and c2 in corr_matrix.columns]
        cov_scores = [cov_matrix.loc[c1, c2] for c1, c2 in pairs if c1 in cov_matrix.columns and c2 in cov_matrix.columns]
        return np.mean(sim_scores) if sim_scores else np.nan, np.mean(cov_scores) if cov_scores else np.nan
    elif len(cats) == 1:
        c = cats[0]
        return 1.0, cov_matrix.loc[c, c] if c in cov_matrix.columns else np.nan
    else:
        return np.nan, np.nan

unique_cats = df_replace['Category'].drop_duplicates()
sim_cov_map = unique_cats.apply(calc_sim_cov)
sim_cov_df = pd.DataFrame(sim_cov_map.tolist(), index=unique_cats.index, columns=['Category_Similarity', 'Category_Covariance'])
sim_cov_df['Category'] = unique_cats

df_replace = pd.merge(df_replace, sim_cov_df, on='Category', how='left')
df_replace = pd.merge(df_replace, trend_agg, on='Identifier', how='left')
df_replace = df_replace.drop(columns=['Date'])

df_replace.to_csv(os.path.join(OUTPUT_DIR, 'arxiv_trend_data_with_features.csv'), index=False, encoding='utf-8-sig')

print("완료되었습니다. arxiv_trend_data_with_features.csv 파일이 생성되었습니다.")
