import os
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib import rcParams
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import PolynomialFeatures

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

print("2. 다항 회귀 (Polynomial Regression) 기반 추세 모델 학습...")
base_date = daily_counts['Created'].min()
daily_counts['day_num'] = (daily_counts['Created'] - base_date).dt.days

poly = PolynomialFeatures(degree=2)
X = daily_counts[['day_num']]
y = daily_counts['MA_7D']
X_poly = poly.fit_transform(X)

model = LinearRegression()
model.fit(X_poly, y)

print("3. 5월 데이터 예측...")
future_dates = pd.date_range(start='2026-05-01', end='2026-05-31')
future_day_nums = (future_dates - base_date).days
future_X = pd.DataFrame({'day_num': future_day_nums})
future_X_poly = poly.transform(future_X)
future_preds = model.predict(future_X_poly)

future_preds = np.maximum(future_preds, 0)

print("4. 그래프 그리기...")
fig, ax = plt.subplots(figsize=(12, 6))

ax.scatter(daily_counts['Created'], daily_counts['count'], alpha=0.2, color='gray', s=10, label='Actual Daily Count')

ax.plot(daily_counts['Created'], daily_counts['MA_7D'], color='#4C72B0', lw=2, label='Actual Trend (7D MA)')

ax.plot(daily_counts['Created'], model.predict(X_poly), color='black', linestyle='--', alpha=0.5, label='Fitted Model (2nd Degree)')

ax.plot(future_dates, future_preds, color='#C44E52', lw=3, label='Forecast for May 2026')

ax.axvspan(pd.Timestamp('2026-05-01'), pd.Timestamp('2026-05-31'), color='#C44E52', alpha=0.1)

ax.set_title("Paper Volume Trend Forecast for May 2026", fontsize=15, fontweight='bold')
ax.set_ylabel("Number of Papers", fontsize=12)
ax.set_xlabel("Date", fontsize=12)

ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
plt.xticks(rotation=45)

ax.grid(axis='y', linestyle='--', alpha=0.7)
ax.legend(fontsize=11, loc='upper left')

may_mean = future_preds.mean()
ax.text(pd.Timestamp('2026-05-15'), future_preds.max(), f"May Predicted Avg:\n{may_mean:.0f} papers/day", 
        color='#C44E52', fontweight='bold', ha='center', va='bottom', fontsize=11,
        bbox=dict(facecolor='white', alpha=0.8, edgecolor='#C44E52'))

fig.tight_layout()
out_png = os.path.join(FIG_DIR, "may_trend_forecast.png")
fig.savefig(out_png, dpi=130)
plt.close(fig)

print(f"   ✓ 완료: {out_png}")
