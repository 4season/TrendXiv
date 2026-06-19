import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import rcParams

from sklearn.preprocessing import StandardScaler
from sklearn.neighbors import KNeighborsClassifier
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import BaggingClassifier, AdaBoostClassifier
from sklearn.metrics import accuracy_score, f1_score, confusion_matrix

rcParams["axes.unicode_minus"] = False

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.join(SCRIPT_DIR, "..", "..")
CSV_DIR = os.path.join(PROJECT_ROOT, "outputs", "csv")
FIG_DIR = os.path.join(PROJECT_ROOT, "outputs", "figures")
INPUT_FILE = os.path.join(CSV_DIR, "arxiv_features_with_titlescore.csv")
RANDOM_STATE = 42

print("1. 데이터 로드...")
df = pd.read_csv(INPUT_FILE)
df['Created'] = pd.to_datetime(df['Created'])

print("2. 전처리 진행 (분야 정규화 및 타겟 구간화)...")
first_cat = df["Category"].astype(str).str.split().str[0]
field_mean_cov = df.groupby(first_cat)["Category_Covariance"].transform("mean")
df["Category_Covariance_norm"] = df["Category_Covariance"] / field_mean_cov

df["Trend_Level"] = pd.qcut(df["Avg_MA_7D"], q=3, labels=["Low", "Mid", "High"])

print("\n3. 시간 기반 데이터 분할 (Train: ~3월, Test: 4월)...")
cutoff_date = pd.Timestamp('2026-03-31')
train_mask = df['Created'] <= cutoff_date
test_mask = df['Created'] > cutoff_date

df_train = df[train_mask]
df_test = df[test_mask]

print(f"   - Train (과거): {len(df_train):,}행")
print(f"   - Test  (미래): {len(df_test):,}행")

full_feats = [
    "DOI_avg_cite_rate", "DOI_is_published", "Paper_Age_Years", 
    "Days_Since_Update", "Title_Char_Count", "Title_Word_Count", 
    "Title_Popularity_Score", "Category_Covariance_norm"
]

X_tr_raw = df_train[full_feats].fillna(0).values
y_tr = df_train["Trend_Level"].astype(str).values

X_te_raw = df_test[full_feats].fillna(0).values
y_te = df_test["Trend_Level"].astype(str).values

scaler = StandardScaler()
X_tr = scaler.fit_transform(X_tr_raw)
X_te = scaler.transform(X_te_raw)

base_tree = DecisionTreeClassifier(max_depth=4, random_state=RANDOM_STATE)

models = {
    "DecisionTree": DecisionTreeClassifier(
        max_depth=8, min_samples_leaf=50, random_state=RANDOM_STATE
    ),
    "KNN (k=11)": KNeighborsClassifier(n_neighbors=11),
    "Bagging": BaggingClassifier(
        estimator=DecisionTreeClassifier(max_depth=8, random_state=RANDOM_STATE),
        n_estimators=50, random_state=RANDOM_STATE, n_jobs=-1
    ),
    "AdaBoost": AdaBoostClassifier(
        estimator=base_tree,
        n_estimators=100, learning_rate=0.5,
        random_state=RANDOM_STATE, algorithm="SAMME"
    ),
}

print("\n4. 모델 학습 및 평가 진행...")
results = {}
for name, m in models.items():
    m.fit(X_tr, y_tr)
    pred = m.predict(X_te)
    acc = accuracy_score(y_te, pred)
    f1 = f1_score(y_te, pred, average="macro")
    results[name] = {"accuracy": acc, "f1_macro": f1}
    print(f"   [{name:<14}] Accuracy: {acc:.3f}, F1(macro): {f1:.3f}")

random_f1 = {
    "DecisionTree": 0.816,
    "KNN (k=11)": 0.668,
    "Bagging": 0.829,
    "AdaBoost": 0.798
}

fig, ax = plt.subplots(figsize=(10, 6))
names = list(results.keys())
x = np.arange(len(names))
w = 0.35

time_f1 = [results[n]["f1_macro"] for n in names]
rand_f1 = [random_f1[n] for n in names]

bars1 = ax.bar(x - w/2, rand_f1, w, label="Random Split (80/20)", color="#4C72B0", edgecolor="black")
bars2 = ax.bar(x + w/2, time_f1, w, label="Time Split (Mar -> Apr)", color="#55A868", edgecolor="black")

ax.set_xticks(x)
ax.set_xticklabels(names, fontsize=11)
ax.set_ylabel("F1 (macro)", fontsize=11)
ax.set_ylim(0, 1.0)
ax.set_title("Performance Comparison: Random Split vs Time Split", fontsize=14, fontweight="bold")
ax.legend(fontsize=10, loc='upper right')

for i in range(len(names)):
    ax.text(i - w/2, rand_f1[i] + 0.015, f"{rand_f1[i]:.3f}", ha="center", fontsize=9)
    ax.text(i + w/2, time_f1[i] + 0.015, f"{time_f1[i]:.3f}", ha="center", fontsize=9, fontweight="bold")

fig.tight_layout()
out_img = os.path.join(FIG_DIR, "time_split_comparison.png")
fig.savefig(out_img, dpi=130)
plt.close(fig)

print(f"\n5. 비교 그래프 저장 완료: {out_img}")
