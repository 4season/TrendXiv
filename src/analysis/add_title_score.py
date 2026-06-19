import os, re
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import rcParams
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA

rcParams["font.family"] = "Noto Sans CJK JP"
rcParams["axes.unicode_minus"] = False

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.join(SCRIPT_DIR, "..", "..")
CSV_DIR = os.path.join(PROJECT_ROOT, "outputs", "csv")
FIG_DIR = os.path.join(PROJECT_ROOT, "outputs", "figures")
os.makedirs(FIG_DIR, exist_ok=True)

print("1. 데이터와 단어 빈도표 로드...")
df = pd.read_csv(os.path.join(CSV_DIR, "arxiv_features_extended.csv"))
wf = pd.read_csv(os.path.join(CSV_DIR, "title_all_words_frequency.csv"))

word_freq = dict(zip(wf["Word"], wf["Frequency"]))

def calc_score(title):
    if pd.isna(title):
        return 0
    clean = re.sub(r"[^a-zA-Z\s]", " ", str(title).lower())
    tokens = clean.split()
    return sum(word_freq.get(w, 0) for w in tokens)

print("2. Title_Popularity_Score 재현 계산...")
df["Title_Popularity_Score"] = df["Title"].apply(calc_score)

out_csv = os.path.join(CSV_DIR, "arxiv_features_with_titlescore.csv")
df.to_csv(out_csv, index=False, encoding="utf-8-sig")
print("   저장:", os.path.basename(out_csv))

print("\n3. 새 점수가 기존 변수와 겹치는지(상관) 점검:")
for col in ["Title_Word_Count", "Title_Char_Count", "CitationCount", "Citation_Percentile"]:
    r = np.corrcoef(df["Title_Popularity_Score"], df[col])[0, 1]
    print(f"   vs {col:<20} 상관 {r:+.3f}")

print("\n4. 점수를 포함해 PCA 재실행...")
features = ['CitationCount','Category_Similarity','Category_Covariance','Avg_MA_7D',
            'Avg_Trend_Speed','Avg_Trend_Acceleration','Paper_Age_Years','Days_Since_Update',
            'Title_Char_Count','Title_Word_Count','Citation_Percentile','DOI_is_published',
            'DOI_avg_citation','Citation_Rate_Annual','DOI_avg_cite_rate',
            'Title_Popularity_Score']

X = df[features].fillna(0).values
Xs = StandardScaler().fit_transform(X)
pca = PCA().fit(Xs)
evr = pca.explained_variance_ratio_
L = pca.components_

ts_idx = features.index("Title_Popularity_Score")
print("\n5. Title_Popularity_Score의 주성분별 기여도:")
for pc in range(4):
    print(f"   PC{pc+1} ({evr[pc]*100:4.1f}%) : {L[pc][ts_idx]:+.3f}")
best_pc = int(np.argmax([abs(L[pc][ts_idx]) for pc in range(len(evr))]))
print(f"   → 가장 강하게 속한 주성분: PC{best_pc+1}")

titles = ["PC1 — 출판 권위·영향력 축", "PC2 — 인용·분야활동 규모 축",
          "PC3 — 제목 길이·스타일 축", "PC4 — 개인성과 ↔ 분야후광 축"]
fig, axes = plt.subplots(2, 2, figsize=(15, 11)); axes = axes.ravel()
for pc in range(4):
    ax = axes[pc]; load = L[pc]
    top = np.argsort(-np.abs(load))[:8]
    top = top[np.argsort(load[top])]
    vals = load[top]; names = [features[i] for i in top]
    colors = ["#4C72B0" if v >= 0 else "#DD8452" for v in vals]
    edges = ["red" if features[i] == "Title_Popularity_Score" else "black" for i in top]
    lws = [2.5 if features[i] == "Title_Popularity_Score" else 0.8 for i in top]
    ax.barh(range(len(vals)), vals, color=colors, edgecolor=edges, linewidth=lws)
    ax.set_yticks(range(len(vals))); ax.set_yticklabels(names, fontsize=11)
    ax.axvline(0, color="black", lw=1); ax.set_xlim(-0.7, 0.7)
    ax.set_title(f"{titles[pc]}  ({evr[pc]*100:.1f}%)", fontsize=14, fontweight="bold", pad=10)
    ax.set_xlabel("기여도 (loading)", fontsize=11)
    for y, v in enumerate(vals):
        ax.text(v + (0.03 if v >= 0 else -0.03), y, f"{v:+.2f}",
                va="center", ha="left" if v >= 0 else "right", fontsize=9)
fig.suptitle("제목 인기점수(Title_Popularity_Score) 포함 — 주성분 4개 (빨간 테두리=새 점수)",
             fontsize=16, fontweight="bold")
fig.tight_layout(rect=[0, 0.01, 1, 0.96])
out_png = os.path.join(FIG_DIR, "5_with_title_score.png")
fig.savefig(out_png, dpi=130); plt.close(fig)
print("   저장:", os.path.basename(out_png))
