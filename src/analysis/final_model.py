import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import rcParams

from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_score
from sklearn.neighbors import KNeighborsClassifier
from sklearn.tree import DecisionTreeClassifier, plot_tree
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
print(f"   - {df.shape[0]:,}행 × {df.shape[1]}열")

print("2. Category_Covariance 분야 내 정규화...")
first_cat = df["Category"].astype(str).str.split().str[0]
field_mean_cov = df.groupby(first_cat)["Category_Covariance"].transform("mean")
df["Category_Covariance_norm"] = df["Category_Covariance"] / field_mean_cov

print("3. 타겟 구간화 (3단계 트렌드)...")
df["Trend_Level"] = pd.qcut(
    df["Avg_MA_7D"], q=3, labels=["Low", "Mid", "High"]
)
print("   - 클래스 분포:")
print(df["Trend_Level"].value_counts().sort_index().to_string())

intrinsic_feats = [
    "DOI_avg_cite_rate",
    "DOI_is_published",
    "Paper_Age_Years",
    "Days_Since_Update",
    "Title_Char_Count",
    "Title_Word_Count",
    "Title_Popularity_Score",
]
full_feats = intrinsic_feats + ["Category_Covariance_norm"]

y = df["Trend_Level"].astype(str)


def run_models(feature_cols, tag):
    """주어진 특징 세트로 4개 분류기를 학습/평가하고 결과 dict 반환."""
    X = df[feature_cols].fillna(0).values
    X_scaled = StandardScaler().fit_transform(X)    # 표준화 (KNN 필수)
    X_tr, X_te, y_tr, y_te = train_test_split(
        X_scaled, y, test_size=0.2, random_state=RANDOM_STATE, stratify=y
    )

    # 의사결정트리 기저 모델 (배깅·부스팅 공용)
    base_tree = DecisionTreeClassifier(max_depth=4, random_state=RANDOM_STATE)

    models = {
        "DecisionTree": DecisionTreeClassifier(
            max_depth=8, min_samples_leaf=50,
            random_state=RANDOM_STATE
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
    out = {}
    print(f"\n   [{tag}] 특징 {len(feature_cols)}개")
    for name, m in models.items():
        # 5-Fold Stratified Cross-Validation 추가
        cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)
        cv_scores = cross_val_score(m, X_scaled, y, cv=cv, scoring="f1_macro", n_jobs=-1)
        cv_mean = np.mean(cv_scores)
        cv_std = np.std(cv_scores)

        m.fit(X_tr, y_tr)
        pred = m.predict(X_te)
        acc = accuracy_score(y_te, pred)
        f1 = f1_score(y_te, pred, average="macro")
        
        out[name] = {
            "accuracy": round(acc, 3), 
            "f1_macro": round(f1, 3),
            "cv_f1_macro_mean": round(cv_mean, 3),
            "cv_f1_macro_std": round(cv_std, 3)
        }
        print(f"      {name:<14} acc={acc:.3f}  f1_macro={f1:.3f}  |  5-Fold CV F1={cv_mean:.3f} (±{cv_std:.3f})")

    return out, models, (X_tr, X_te, y_tr, y_te)


print("\n4. 모델 학습/평가...")
res_full, models_full, (Xtr_f, Xte_f, ytr_f, yte_f) = run_models(full_feats, "FULL (분야특징 포함)")
res_intr, models_intr, _ = run_models(intrinsic_feats, "INTRINSIC (논문 고유만)")

print("\n5. 그래프 저장...")

fig, ax = plt.subplots(figsize=(6, 4))
order = ["Low", "Mid", "High"]
counts = df["Trend_Level"].value_counts().reindex(order)
colors = ["#9ec9e2", "#4C72B0", "#2a4d69"]
ax.bar(order, counts.values, color=colors, edgecolor="black")
ax.set_title("Target Class Distribution (Avg_MA_7D -> 3 levels)", fontsize=13, fontweight="bold")
ax.set_ylabel("Number of Papers")
ax.set_xlabel("Trend Level")
for i, v in enumerate(counts.values):
    ax.text(i, v + 300, f"{v:,}", ha="center", fontsize=10)
fig.tight_layout()
fig.savefig(os.path.join(FIG_DIR, "final_1_class_distribution.png"), dpi=130)
plt.close(fig)
print("   ✓ final_1_class_distribution.png")

fig, ax = plt.subplots(figsize=(10, 5.5))
names = list(res_full.keys())
x = np.arange(len(names))
w = 0.35
f1_full = [res_full[n]["f1_macro"] for n in names]
f1_intr = [res_intr[n]["f1_macro"] for n in names]

bars1 = ax.bar(x - w/2, f1_full, w, label="Full (with field feature)",
               color="#4C72B0", edgecolor="black")
bars2 = ax.bar(x + w/2, f1_intr, w, label="Intrinsic only",
               color="#DD8452", edgecolor="black")

ax.set_xticks(x)
ax.set_xticklabels(names, fontsize=11)
ax.set_ylabel("F1 (macro)", fontsize=11)
ax.set_ylim(0, 1)
ax.set_title("Model Comparison - Field Feature Contribution", fontsize=13, fontweight="bold")
ax.legend(fontsize=10)

for i in range(len(names)):
    ax.text(i - w/2, f1_full[i] + 0.015, f"{f1_full[i]:.3f}",
            ha="center", fontsize=9, fontweight="bold")
    ax.text(i + w/2, f1_intr[i] + 0.015, f"{f1_intr[i]:.3f}",
            ha="center", fontsize=9)

best_idx = np.argmax(f1_full)
ax.annotate("★ Best", xy=(best_idx - w/2, f1_full[best_idx] + 0.04),
            fontsize=10, ha="center", color="#C44E52", fontweight="bold")

fig.tight_layout()
fig.savefig(os.path.join(FIG_DIR, "final_2_model_comparison.png"), dpi=130)
plt.close(fig)
print("   ✓ final_2_model_comparison.png")

dt_model = models_full["DecisionTree"]
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.5))

cm = confusion_matrix(yte_f, dt_model.predict(Xte_f), labels=order)
im = ax1.imshow(cm, cmap="Blues")
ax1.set_xticks(range(3)); ax1.set_xticklabels(order, fontsize=11)
ax1.set_yticks(range(3)); ax1.set_yticklabels(order, fontsize=11)
ax1.set_xlabel("Predicted", fontsize=11)
ax1.set_ylabel("Actual", fontsize=11)
ax1.set_title("Confusion Matrix - Decision Tree (Full)", fontsize=12, fontweight="bold")
for i in range(3):
    for j in range(3):
        ax1.text(j, i, f"{cm[i, j]:,}", ha="center", va="center",
                 color="white" if cm[i, j] > cm.max()/2 else "black", fontsize=11)
fig.colorbar(im, ax=ax1, fraction=0.046, pad=0.04)

imp = dt_model.feature_importances_
oi = np.argsort(imp)
feat_colors = ["#C44E52" if full_feats[i] == "Category_Covariance_norm"
               else "#55A868" for i in oi]
ax2.barh(np.array(full_feats)[oi], imp[oi], color=feat_colors, edgecolor="black")
ax2.set_title("Feature Importance - Decision Tree (Full)", fontsize=12, fontweight="bold")
ax2.set_xlabel("Importance", fontsize=11)
for idx, (val, name) in enumerate(zip(imp[oi], np.array(full_feats)[oi])):
    ax2.text(val + 0.005, idx, f"{val:.3f}", va="center", fontsize=9)

fig.tight_layout()
fig.savefig(os.path.join(FIG_DIR, "final_3_confusion_importance.png"), dpi=130)
plt.close(fig)
print("   ✓ final_3_confusion_importance.png")

fig, ax = plt.subplots(figsize=(22, 10))
plot_tree(
    dt_model,
    feature_names=full_feats,
    class_names=order,
    filled=True,
    rounded=True,
    fontsize=8,
    max_depth=3,
    ax=ax,
    impurity=True,
    proportion=True,
)
ax.set_title("Decision Tree Structure (top 3 levels, pruned)", fontsize=14, fontweight="bold")
fig.tight_layout()
fig.savefig(os.path.join(FIG_DIR, "final_4_decision_tree.png"), dpi=130)
plt.close(fig)
print("   ✓ final_4_decision_tree.png")

best_name = max(res_full, key=lambda k: res_full[k]["f1_macro"])
print("\n" + "=" * 64)
print(" 최종 모델 요약")
print("=" * 64)
print(f" · 타겟        : Avg_MA_7D → 3단계 (Low/Mid/High)")
print(f" · 특징(FULL)  : {len(full_feats)}개 {full_feats}")
print(f" · 메인 모델   : DecisionTree (max_depth=8, min_samples_leaf=50)")
print(f"   - acc={res_full['DecisionTree']['accuracy']}  "
      f"f1={res_full['DecisionTree']['f1_macro']}")

print(f"\n [모델별 성능 비교 (FULL)]")
for name in names:
    flag = " ★" if name == best_name else ""
    print(f"   {name:<14} acc={res_full[name]['accuracy']:.3f}  "
          f"f1={res_full[name]['f1_macro']:.3f}{flag}")

print(f"\n [분야특징 기여도 (FULL vs INTRINSIC)]")
for name in names:
    diff = res_full[name]["f1_macro"] - res_intr[name]["f1_macro"]
    print(f"   {name:<14} f1 차이: {diff:+.3f}")

print("=" * 64)
