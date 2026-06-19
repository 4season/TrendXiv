import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.join(SCRIPT_DIR, "..", "..")
CSV_DIR = os.path.join(PROJECT_ROOT, "outputs", "csv")
FIG_DIR = os.path.join(PROJECT_ROOT, "outputs", "figures")
INPUT_FILE = os.path.join(CSV_DIR, "arxiv_features_with_titlescore.csv")

print("1. 데이터 로드 중...")
df = pd.read_csv(INPUT_FILE)

features = [
    "CitationCount",
    "Category_Similarity", "Category_Covariance",
    "Avg_MA_7D", "Avg_Trend_Speed", "Avg_Trend_Acceleration",
    "Paper_Age_Years", "Days_Since_Update",
    "Title_Char_Count", "Title_Word_Count",
    "Citation_Percentile",
    "DOI_is_published", "DOI_avg_citation",
    "Citation_Rate_Annual", "DOI_avg_cite_rate",
]
X = df[features].fillna(0).values
print(f"   - PCA 입력: {X.shape[0]:,}행 × {X.shape[1]}개 특징")

print("2. [비교1] 표준화 전 vs 후 PCA 계산 중...")

pca_raw = PCA(n_components=X.shape[1]).fit(X)

X_std = StandardScaler().fit_transform(X)
pca_std = PCA(n_components=X.shape[1]).fit(X_std)

def top_driver(pca_model):
    load = np.abs(pca_model.components_[0])
    i = int(load.argmax())
    return features[i], load[i]

raw_feat, raw_w = top_driver(pca_raw)
std_feat, std_w = top_driver(pca_std)
print(f"   - 표준화 전 PC1 지배 변수: {raw_feat} (기여 가중치 {raw_w:.2f})")
print(f"   - 표준화 후 PC1 지배 변수: {std_feat} (기여 가중치 {std_w:.2f})")

fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
for ax, model, title, dom_feat, dom_w in [
    (axes[0], pca_raw, "BEFORE scaling (raw)", raw_feat, raw_w),
    (axes[1], pca_std, "AFTER scaling (standardized)", std_feat, std_w),
]:
    ratios = model.explained_variance_ratio_[:8] * 100
    ax.bar(range(1, len(ratios) + 1), ratios, color="#4C72B0", edgecolor="black")
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.set_xlabel("Principal Component")
    ax.set_ylabel("Explained Variance (%)")
    ax.set_ylim(0, 100)
    for i, v in enumerate(ratios):
        ax.text(i + 1, v + 2, f"{v:.0f}%", ha="center", fontsize=9)
    ax.annotate(f"PC1 dominant: {dom_feat}\n(weight {dom_w:.2f})",
                xy=(1, ratios[0]), xytext=(3.5, ratios[0] * 0.85),
                fontsize=8, color="#C44E52", fontweight="bold",
                arrowprops=dict(arrowstyle="->", color="#C44E52", lw=1.2),
                ha="center")
fig.suptitle("PCA: Why Standardization Matters", fontsize=14, fontweight="bold")
fig.tight_layout()
fig.savefig(os.path.join(FIG_DIR, "1_compare_standardization.png"), dpi=130)
plt.close(fig)

print("3. 표준화 기반 본 PCA 분석 중...")
pca = pca_std
evr = pca.explained_variance_ratio_
cum = np.cumsum(evr)

n_80 = int(np.argmax(cum >= 0.80) + 1)
print(f"   - PC1 설명력: {evr[0]*100:.1f}% / PC1+PC2: {cum[1]*100:.1f}%")
print(f"   - 누적 80% 도달에 필요한 주성분 수: {n_80}개")

fig, ax = plt.subplots(figsize=(9, 5))
xs = range(1, len(evr) + 1)
ax.bar(xs, evr * 100, color="#55A868", edgecolor="black", label="Each PC")
ax.plot(xs, cum * 100, color="#C44E52", marker="o", label="Cumulative")
ax.axhline(80, color="gray", ls="--", lw=1)
ax.text(len(evr), 82, "80% line", ha="right", color="gray")
ax.axvline(n_80, color="#4C72B0", ls=":", lw=1.5, alpha=0.7)
ax.text(n_80 + 0.3, 50, f"← PC{n_80} (cutoff)", fontsize=10,
        color="#4C72B0", fontweight="bold")
for i, v in enumerate(evr * 100):
    if v >= 1:
        ax.text(i + 1, v + 1.5, f"{v:.1f}%", ha="center", fontsize=8)
ax.set_xlabel("Principal Component")
ax.set_ylabel("Explained Variance (%)")
ax.set_title("Scree Plot — How many components do we need?",
             fontsize=13, fontweight="bold")
ax.legend()
fig.tight_layout()
fig.savefig(os.path.join(FIG_DIR, "2_scree_plot.png"), dpi=130)
plt.close(fig)

print("4. PC1-PC2 산점도 및 변수 기여도 그래프 생성 중...")
scores = pca.transform(X_std)
loadings = pca.components_

rng = np.random.default_rng(42)
idx = rng.choice(len(scores), size=4000, replace=False)

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 7),
                                gridspec_kw={"width_ratios": [1, 1.2]})

pc1_vals = scores[idx, 0]
pc2_vals = scores[idx, 1]
xlim_hi = np.percentile(pc1_vals, 99.5) * 1.15
xlim_lo = np.percentile(pc1_vals, 0.5) * 1.15
ylim_hi = np.percentile(pc2_vals, 99.5) * 1.15
ylim_lo = np.percentile(pc2_vals, 0.5) * 1.15

pub = df["DOI_is_published"].values[idx]
for val, color, lab in [(0, "#DD8452", "arXiv only"), (1, "#4C72B0", "Published")]:
    m = pub == val
    ax1.scatter(scores[idx][m, 0], scores[idx][m, 1], s=8, alpha=0.35,
                c=color, label=lab)
ax1.set_xlim(xlim_lo, xlim_hi)
ax1.set_ylim(ylim_lo, ylim_hi)

n_outlier = ((pc1_vals > xlim_hi) | (pc1_vals < xlim_lo) |
             (pc2_vals > ylim_hi) | (pc2_vals < ylim_lo)).sum()
if n_outlier > 0:
    ax1.text(0.98, 0.02, f"({n_outlier} outliers clipped)",
             transform=ax1.transAxes, ha="right", va="bottom",
             fontsize=8, color="gray", fontstyle="italic")

ax1.set_xlabel(f"PC1 ({evr[0]*100:.1f}%)", fontsize=11)
ax1.set_ylabel(f"PC2 ({evr[1]*100:.1f}%)", fontsize=11)
ax1.set_title("Papers in PC1-PC2 space", fontsize=12, fontweight="bold")
ax1.legend()
ax1.axhline(0, color="gray", lw=0.5)
ax1.axvline(0, color="gray", lw=0.5)

n_pc = 4
hm = loadings[:n_pc].T
im = ax2.imshow(hm, cmap="RdBu_r", vmin=-0.6, vmax=0.6, aspect="auto")
ax2.set_xticks(range(n_pc))
ax2.set_xticklabels([f"PC{i+1}" for i in range(n_pc)], fontsize=11)
ax2.set_yticks(range(len(features)))
ax2.set_yticklabels(features, fontsize=10)
ax2.set_title("Feature contribution (loadings)", fontsize=12, fontweight="bold")
for i in range(len(features)):
    for j in range(n_pc):
        ax2.text(j, i, f"{hm[i, j]:.2f}", ha="center", va="center",
                 fontsize=9, color="black")
fig.colorbar(im, ax=ax2, fraction=0.046, pad=0.04, label="loading")
fig.tight_layout()
fig.savefig(os.path.join(FIG_DIR, "3_pca_scatter_loadings.png"), dpi=130)
plt.close(fig)

print("\n" + "=" * 60)
print(" PCA 분석 결과 요약")
print("=" * 60)
print(f" · 표준화 전 PC1 설명력: {pca_raw.explained_variance_ratio_[0]*100:.1f}% "
      f"(지배변수 {raw_feat})")
print(f" · 표준화 후 PC1 설명력: {evr[0]*100:.1f}% (지배변수 {std_feat})")
print(f" · 표준화 후 PC1+PC2 누적 설명력: {cum[1]*100:.1f}%")
print(f" · 누적 80% 도달 주성분 수: {n_80}개 (→ {X.shape[1]}개를 {n_80}개로 압축 가능)")

print("\n[PC1 상위 기여 변수 5개]")
order1 = np.argsort(-np.abs(loadings[0]))[:5]
for i in order1:
    print(f"   {features[i]:<22} {loadings[0][i]:+.3f}")

print("\n[PC2 상위 기여 변수 5개]")
order2 = np.argsort(-np.abs(loadings[1]))[:5]
for i in order2:
    print(f"   {features[i]:<22} {loadings[1][i]:+.3f}")
print("=" * 60)
