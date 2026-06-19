import os
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib import rcParams

from sklearn.tree import DecisionTreeRegressor
from sklearn.neighbors import KNeighborsRegressor
from sklearn.ensemble import AdaBoostRegressor

rcParams["axes.unicode_minus"] = False

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.join(SCRIPT_DIR, "..", "..")
CSV_DIR = os.path.join(PROJECT_ROOT, "outputs", "csv")
FIG_DIR = os.path.join(PROJECT_ROOT, "outputs", "figures")
INPUT_FILE = os.path.join(CSV_DIR, "arxiv_features_with_titlescore.csv")

print("1. 데이터 로드 및 집계...")
df = pd.read_csv(INPUT_FILE)
df['Created'] = pd.to_datetime(df['Created'])

df = df[df['Created'] >= '2025-06-01'].copy()

daily_counts = df.groupby('Created').size().reset_index(name='count')
daily_counts = daily_counts.sort_values('Created').set_index('Created')
idx = pd.date_range(daily_counts.index.min(), daily_counts.index.max())
daily_counts = daily_counts.reindex(idx, fill_value=0)
daily_counts['MA_7D'] = daily_counts['count'].rolling(window=7, min_periods=1).mean()
daily_counts = daily_counts.reset_index().rename(columns={'index': 'Created'})

print("2. 수업 범위 내 회귀 모델들 학습...")
base_date = daily_counts['Created'].min()
daily_counts['day_num'] = (daily_counts['Created'] - base_date).dt.days

X = daily_counts[['day_num']]
y = daily_counts['MA_7D']

models = {
    "Decision Tree": DecisionTreeRegressor(max_depth=5, random_state=42),
    "KNN (k=7)": KNeighborsRegressor(n_neighbors=7),
    "AdaBoost": AdaBoostRegressor(
        estimator=DecisionTreeRegressor(max_depth=5),
        n_estimators=50, random_state=42
    )
}

for name, m in models.items():
    m.fit(X, y)

print("3. 5월 데이터 예측 (미래 외삽)...")
future_dates = pd.date_range(start='2026-05-01', end='2026-05-31')
future_day_nums = (future_dates - base_date).days
future_X = pd.DataFrame({'day_num': future_day_nums})

all_dates = pd.concat([pd.Series(daily_counts['Created']), pd.Series(future_dates)])
all_X = pd.DataFrame({'day_num': (all_dates - base_date).dt.days})

print("4. 그래프 그리기...")
fig, ax = plt.subplots(figsize=(14, 7))

ax.plot(daily_counts['Created'], daily_counts['MA_7D'], color='black', lw=3, label='Actual Trend (7D MA)')

colors = {'Decision Tree': '#4C72B0', 'KNN (k=7)': '#55A868', 'AdaBoost': '#C44E52'}
styles = {'Decision Tree': '--', 'KNN (k=7)': '-.', 'AdaBoost': ':'}

for name, m in models.items():
    preds = m.predict(all_X)
    ax.plot(all_dates, preds, color=colors[name], linestyle=styles[name], lw=2, label=f'{name} Forecast')

ax.axvspan(pd.Timestamp('2026-05-01'), pd.Timestamp('2026-05-31'), color='gray', alpha=0.1)
ax.text(pd.Timestamp('2026-05-15'), ax.get_ylim()[1]*0.9, "May Forecast Area\n(Extrapolation)", 
        ha='center', va='top', fontsize=12, fontweight='bold', color='gray')

ax.set_title("Time Series Forecasting with Class Models (DT, KNN, AdaBoost)", fontsize=15, fontweight='bold')
ax.set_ylabel("Number of Papers (Daily MA)", fontsize=12)
ax.set_xlabel("Date", fontsize=12)

ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
plt.xticks(rotation=45)

ax.grid(axis='y', linestyle='--', alpha=0.7)
ax.legend(fontsize=11, loc='upper left')

info_text = (
    "[Key Observation]\n"
    "Tree-based and Distance-based models CANNOT extrapolate.\n"
    "They only predict values seen during training.\n"
    "Thus, they flatline in May instead of following the upward trend."
)
ax.text(pd.Timestamp('2025-06-15'), ax.get_ylim()[1]*0.8, info_text, 
        fontsize=11, bbox=dict(facecolor='lightyellow', alpha=0.8, edgecolor='black'))

fig.tight_layout()
out_png = os.path.join(FIG_DIR, "may_trend_class_models.png")
fig.savefig(out_png, dpi=130)
plt.close(fig)

print(f"   ✓ 완료: {out_png}")
