import pandas as pd
import re
from collections import Counter
import os
import matplotlib.pyplot as plt

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.join(SCRIPT_DIR, "..", "..")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "outputs", "csv")
file_path = os.path.join(OUTPUT_DIR, "arxiv_trend_data.csv")

print("1. 데이터 로드 중...")
df = pd.read_csv(file_path)

STOPWORDS = set([
    'a', 'an', 'the', 'and', 'but', 'if', 'or', 'because', 'as', 'what',
    'which', 'this', 'that', 'these', 'those', 'then', 'so', 'than', 'such',
    'both', 'with', 'by', 'for', 'about', 'against', 'between', 'into', 'through',
    'during', 'before', 'after', 'above', 'below', 'to', 'from', 'up', 'down',
    'in', 'out', 'on', 'off', 'over', 'under', 'again', 'further', 'then', 'once',
    'here', 'there', 'when', 'where', 'why', 'how', 'all', 'any', 'both', 'each',
    'few', 'more', 'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only',
    'own', 'same', 'so', 'than', 'too', 'very', 'can', 'will', 'just', 'should',
    'now', 'of', 'at', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have',
    'has', 'had', 'do', 'does', 'did', 'via', 'using', 'based', 'approach'
])

print("2. 제목 텍스트 전처리 및 단어 추출 중...")
all_words = []

for title in df['Title'].dropna():
    clean_title = re.sub(r'[^a-zA-Z\s]', ' ', str(title).lower())
    tokens = clean_title.split()
    filtered_tokens = [w for w in tokens if w not in STOPWORDS and len(w) > 1]
    all_words.extend(filtered_tokens)

print("3. 단어 빈도수 계산 중...")
word_counts = Counter(all_words)
all_word_counts = word_counts.most_common()

output_file = os.path.join(OUTPUT_DIR, "title_all_words_frequency.csv")
df_words = pd.DataFrame(all_word_counts, columns=['Word', 'Frequency'])
df_words.to_csv(output_file, index=False, encoding='utf-8-sig')

print("\n==============================================")
print(f" 총 {len(all_word_counts):,}개의 고유 단어 빈도수를 계산했습니다.")
print(f" 전체 순위 결과가 'title_all_words_frequency.csv' 파일에 저장되었습니다.")
print("==============================================")

top_words = all_word_counts[:50]

print("\n[미리보기] Title에서 가장 자주 등장하는 단어 Top 50")
print("----------------------------------------------")

top_50_avg = 0
for rank, (word, count) in enumerate(top_words, 1):
    print(f"{rank:2d}위: {word:<15} (빈도: {count:,}번)")
    top_50_avg += count

print("----------------------------------------------")
print(f"      Top 50 평균 빈도수: {top_50_avg/len(top_words):,.2f}번")
print("==============================================")

all_words_avg = 0
valid_word_count = 0

for rank, (word, count) in enumerate(all_word_counts, 1):
    if count <= 2:
        continue
    
    all_words_avg += count
    valid_word_count += 1

print("----------------------------------------------")
print(f"      2회 이상 등장 단어 평균 빈도수: {all_words_avg / valid_word_count:,.2f}번")
print("==============================================")

frequencies = [count for word, count in all_word_counts]
freq_series = pd.Series(frequencies)

counts, bins, patches = plt.hist(freq_series, bins=50, log=True, color='skyblue', edgecolor='black')

print("\n----------------------------------------------")
print("               막대(Bin)별 세부 정보                ")
print("----------------------------------------------")
for i in range(len(counts)):
    if counts[i] > 0:
        print(f"빈도수 {bins[i]:>6.1f} ~ {bins[i+1]:>6.1f}번 구간: {int(counts[i]):,}개의 단어")
print("==============================================")

plt.title("Word Frequency Distribution (Log Scale)")
plt.xlabel("Frequency")
plt.ylabel("Number of Words (Log Scale)")
plt.show()

word_freq_dict = dict(all_word_counts)

def calculate_title_popularity(title):
    if pd.isna(title):
        return 0
    clean_title = re.sub(r'[^a-zA-Z\s]', ' ', str(title).lower())
    tokens = clean_title.split()
    score = sum(word_freq_dict.get(w, 0) for w in tokens)
    return score

print("새로운 성분 'Title_Popularity_Score'를 계산 중입니다...")
df['Title_Popularity_Score'] = df['Title'].apply(calculate_title_popularity)

print("\n==============================================")
print("     트렌디한 단어를 가장 많이 쓴 논문 Top 5")
print("==============================================")
top_trendy_papers = df.sort_values(by='Title_Popularity_Score', ascending=False).head(5)

for idx, row in top_trendy_papers.iterrows():
    print(f"점수: {row['Title_Popularity_Score']:,}점 | 제목: {row['Title']}")
