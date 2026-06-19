# TrendXiv 소스코드 상세 해설 백서
> **TrendXiv Source Code Architecture and Implementation Details**

본 문서는 TrendXiv 프로젝트의 데이터 수집, 병합, 전처리 및 분석과 기계학습 모델링을 담당하는 각 소스코드의 내부 로직과 소스코드에 포함된 주요 주석, 파라미터 선정 근거를 가독성 있게 정리한 백서입니다.

---

## 1. 데이터 수집 단계 (Data Collection)

### src/collect/main.py (arXiv 데이터 수집 모듈)
- **개요**: arXiv OAI-PMH API를 활용하여 컴퓨터 과학(cs) 분야의 논문 메타데이터를 XML 형식으로 배치 수집하여 CSV로 기록합니다.
- **주요 로직 및 알고리즘**:
  - `ListRecords` 동사(verb)와 `metadataPrefix=arXiv` 스펙을 사용해 OAI-PMH 프로토콜로 요청합니다.
  - OAI-PMH의 페이지네이션 표준인 `resumptionToken`을 감지하여 다음 페이지의 데이터를 연속적으로 수집합니다.
  - XML 엘리먼트 파싱 시, 동적으로 변경될 수 있는 XML 네임스페이스 URI를 정규표현식(`\{(.*)\}`)으로 자동 추출하여 네임스페이스 파싱 에러를 예방합니다.
- **핵심 주석 설명 및 제약 통제**:
  - `서버 배려를 위해 5초 대기합니다...` : arXiv API 호출 가이드라인에 따라 과도한 요청으로 인한 IP 차단을 방지하기 위해 배치 요청 사이에 5초의 강제 지연 시간을 둡니다.
  - `metadata_container가 None이거나 길이가 0일 때 skip` : arXiv 시스템상 삭제된(Deleted) 논문은 메타데이터 컨테이너 내부가 비어있기 때문에 예외 처리하여 수집 에러를 방지합니다.
  - HTTP 에러 발생 시, 30초 대기 후 재시도하는 네트워크 Transient 에러 복구 루프가 주석과 함께 구현되어 있습니다.

---

## 2. 데이터 병합 단계 (Data Merger)

### src/merge/merge_citations.go (인용 데이터 병합 모듈)
- **개요**: Go 언어를 사용하여 Semantic Scholar API와 로컬 JSON 캐시 시스템을 통해 수만 건의 arXiv 논문에 대한 DOI 및 인용 수(Citation Count)를 병합하는 배치 프로세서입니다.
- **주요 로직 및 알고리즘**:
  - **아토믹 캐시(Atomic Cache)**: 메모리상의 캐시 데이터를 로컬 JSON(`citations_cache.json`)으로 저장할 때, 임시 파일(`.tmp`)을 생성한 후 `os.Rename` 함수로 원본을 원자적 덮어쓰기하여 파일 쓰기 도중 프로그램이 예기치 않게 종료되어도 기존 캐시 데이터가 오염되는 것을 완벽히 방지합니다.
  - **동적 지연 속도 제어**: API Key 소유 여부에 따라 호출 속도를 자동으로 변동합니다.
    - API Key 보유 시: 1.2초(1200ms) 지연 (초당 1회 API 호출 한도 준수)
    - API Key 미보유 시: 3.0초(3000ms) 지연 (비인증 IP 차단 방지)
  - **지수 백오프(Exponential Backoff) 재시도**: API 호출 시 429(Too Many Requests) 혹은 5xx 서버 에러가 감지되면, 기본 2초부터 시작하여 에러 발생 시마다 대기 시간을 2배씩 늘려가며(최대 5회) 재시도하여 대규모 배치 처리 도중 네트워크 단절로 전체 파이프라인이 멈추는 것을 통제합니다.
- **핵심 주석 및 가이드라인**:
  - `Strip version` : arXiv ID 뒤에 붙는 버전 표기(예: `1703.01504v1` -> `1703.01504`)를 제거하여 API 쿼리 성공률과 매핑 정확도를 높입니다.
  - API로부터 조회가 실패하거나 검색 결과가 없는 논문은 `DOI: 10.48550/arXiv.[ID]`, `CitationCount: 0`과 같이 기본값(Fallback)을 생성해 캐시에 기록함으로써, 재실행 시 중복 쿼리를 실행하지 않도록 최적화되어 있습니다.

---

## 3. 전처리 및 피처 엔지니어링 단계 (Preprocessing)

### src/preprocess/preprocess.py (시계열 및 상관도 파생변수 생성 모듈)
- **개요**: 수집된 논문 데이터로부터 카테고리별 일간 논문 빈도를 구하고, 분야 간 공분산과 유사도 및 시계열 트렌드 피처(이동평균, 속도, 가속도)를 연산하여 병합합니다.
- **주요 로직 및 알고리즘**:
  - **다중 카테고리 폭파(Exploding)**: arXiv 논문은 여러 카테고리에 속할 수 있으므로, 공분산 및 시계열 계산을 위해 카테고리를 공백으로 스플릿한 후 개별 행으로 확장(Explode)하여 카테고리별 일별 통계 수치를 집계합니다.
  - **공분산 및 상관도 연산**: 피벗된 일별 카테고리 논문 수 매트릭스를 기반으로 `.cov()` 및 `.corr()` 메서드를 활용하여 카테고리 쌍 간의 공분산과 피어슨 상관계수 행렬을 계산합니다.
  - **시계열 파생변수 계산**:
    - **이동평균(MA_7D)**: 일별 수치의 7일 롤링 평균 적용 (노이즈 스무딩)
    - **트렌드 속도(Trend_Speed)**: 7일 이동평균 수치에 대한 1차 차분 (1일간 관심도 변화량)
    - **트렌드 가속도(Trend_Acceleration)**: 트렌드 속도에 대한 2차 차분 (변화량의 변화량)
  - **다중 카테고리 재집계**: 다중 카테고리를 가진 논문의 경우, 해당 카테고리 쌍 간의 유사도/공분산의 평균을 구하고 시계열 피처들 역시 해당 분야들의 평균값(`Avg_MA_7D`, `Avg_Trend_Speed`, `Avg_Trend_Acceleration`)으로 변환하여 논문 식별자(Identifier) 단위로 재결합합니다.

### src/preprocess/title_word_count.py (제목 텍스트 토큰 분석 모듈)
- **개요**: 논문 제목의 단어들을 추출하여 전체 단어 빈도 사전을 구축하고 단어 빈도 분석 플롯을 시각화합니다.
- **주요 로직 및 알고리즘**:
  - 알파벳 문자를 제외한 기호와 특수문자를 정규표현식(`[^a-zA-Z\s]`)으로 제거하고 소문자로 통일합니다.
  - 불용어(Stopwords) 사전을 직접 정의하여 `the`, `of`, `and`, `to` 등 저정보 단어들을 제거하여 정보 순도를 향상시킵니다.
  - 단어 빈도를 세어 `title_all_words_frequency.csv`로 저장하고, 상위 30개 단어의 빈도를 시각화하여 `word_frequency.png`로 출력합니다.

---

## 4. 탐색적 데이터 분석 단계 (Exploratory Data Analysis)

### src/analysis/add_title_score.py (제목 인기 점수 PCA 통합 모듈)
- **개요**: 단어 빈도 사전을 바탕으로 각 논문 제목의 단어 인기 합산 점수인 `Title_Popularity_Score`를 계산하고 이를 포함하여 PCA를 수행합니다.
- **주요 로직 및 알고리즘**:
  - 각 논문 제목을 토큰화한 후 단어 빈도 사전을 룩업하여 모든 단어의 빈도 누적 합계를 구해 `Title_Popularity_Score`로 피처화합니다.
  - 새로 생성한 피처를 기존 15개 피처와 융합하여 16차원 StandardScaler 표준화를 진행하고 PCA 모델을 학습시킵니다.
- **핵심 주석 설명**:
  - `Title_Popularity_Score`와 기존 피처(`Title_Word_Count`, `Title_Char_Count`, `CitationCount`, `Citation_Percentile`) 간의 피어슨 상관계수를 체크하여 독립성을 검증합니다.
  - 기여도 분석 주석: `Title_Popularity_Score`가 PC2(인용/분야활동 규모 축)와 PC3(제목 스타일 축) 등에 강하게 걸친 주성분 로딩 벡터 구조를 해석하고 그래프로 저장합니다.

### src/analysis/pca_analysis.py (표준화 비교 및 탐색적 PCA 모듈)
- **개요**: 머신러닝 모델 투입 전 15개 피처에 대한 표준화(Scaling) 유무에 따른 주성분 왜곡 현상을 입증하고 데이터 구조를 시각화합니다.
- **주요 로직 및 알고리즘**:
  - **표준화 전 vs 표준화 후 분산 분석**: 표준화를 거치지 않았을 때 단일 대분산 피처(`Category_Covariance`)가 PC1의 분산 설명력을 80% 이상 강탈하는 왜곡 현상을 수치화하여 입증합니다.
  - **Scree Plot**: 누적 분산 설명력 곡선과 각 PC의 기여도를 막대그래프로 나타내어 80%의 정보를 유지하기 위해 총 7개의 주성분이 필요하다는 결론을 내립니다.
  - **로딩 벡터(Loadings) 플롯**: 각 차원(PC1~PC4)에서 피처들이 갖는 방향 가중치를 시각화하여 변수 간 묶임 구조(예: 인용 규모 축, 논문 스타일 축 등)를 도메인적으로 정의합니다.

---

## 5. 예측 및 기계학습 검증 단계 (Modeling & Verification)

### src/analysis/final_model.py (최종 기계학습 분류 파이프라인)
- **개요**: 분야 정규화 기법을 적용한 8개 피처를 입력으로 하여 논문의 트렌드 등급(Low, Mid, High)을 예측하고, 수업 범위 내 4개 핵심 모델의 성능을 비교합니다.
- **주요 로직 및 알고리즘**:
  - **분야 내 정규화**: `Category_Covariance`를 대분야 평균으로 나누어 준 `Category_Covariance_norm`을 계산하여 분야 자체의 규모 지배 편향을 보정합니다.
  - **타겟 분위수 분할**: `Avg_MA_7D`를 3분위수로 고르게 분할하여 클래스 불균형을 해결한 타겟 `Trend_Level`을 설정합니다.
  - **5-Fold Stratified Cross-Validation**: Holdout 검증 외에 데이터의 계층 비율을 유지하는 5-Fold Stratified K-폴드 교차 검증을 강제 적용해 평균 F1-Score와 표준편차를 도출하여 일반화 신뢰도를 크로스체크합니다.
- **핵심 파라미터 설정 및 가지치기(Pruning) 근거**:
  - `DecisionTreeClassifier(max_depth=8, min_samples_leaf=50)`:
    - `max_depth=8`: 사전 가지치기 설정. 4, 6, 8로 단계를 실험한 결과 검증 F1 점수가 8 depth 부근에서 수렴하여 최적 파라미터로 안착했습니다.
    - `min_samples_leaf=50`: 단일 리프 노드가 가져야 할 최소 샘플 수를 전체 데이터의 약 0.06% 수준인 50개로 제한함으로써, 노이즈 데이터에 의한 과적합을 방지하고 일반화 성능을 유도합니다.
  - `KNeighborsClassifier(n_neighbors=11)`:
    - 동점(Tie) 투표에 의한 애매모호함을 해결하기 위해 홀수인 $k=11$로 선정하여 다수결 분류 안정성을 꾀했습니다.
  - `BaggingClassifier(estimator=DecisionTreeClassifier(max_depth=8), n_estimators=50)`:
    - 단일 의사결정트리의 높은 분산(Variance) 문제를 극복하기 위해 부트스트랩 샘플링을 적용한 50개의 트리를 배깅 앙상블하여 성능을 가장 극대화(F1 0.816)했습니다.
  - `AdaBoostClassifier(estimator=DecisionTreeClassifier(max_depth=4), n_estimators=100, learning_rate=0.5, algorithm="SAMME")`:
    - 약한 학습기로 `max_depth=4`인 트리를 순차 보완 기법으로 학습시켜 AdaBoost를 구성했습니다.

### src/analysis/time_split_model.py (시간 분할 및 도메인 시프트 검증 모듈)
- **개요**: 랜덤 분할의 미래 참조 오류(Data Leakage)를 방지하기 위해 특정 날짜 기준으로 데이터를 분리하여 현실 배포 성능을 평가합니다.
- **주요 로직 및 알고리즘**:
  - **시간 분할 마스킹**: 등록일 `Created`가 `2026-03-31` 이하인 과거 데이터(61,842건)를 Train Set으로, `2026-04-01` 이후인 미래 데이터(20,846건)를 Test Set으로 분할합니다.
  - Train Set에서 `StandardScaler`를 학습(fit)시킨 스케일러로 Test Set을 변환(transform)함으로써, 미래 정보의 사전 노출을 원천 차단합니다.
  - 랜덤 분할 대비 F1-Score가 소폭 하락(DecisionTree F1: 0.809 -> 0.772)함을 보여주어 현실적인 시간 경과에 따른 성능 추이를 명시합니다.

### src/analysis/forecast_trend.py (참고용 다항 회귀 예측 모듈)
- **개요**: 전체 논문 발생 트렌드를 시계열 다항식으로 피팅하여 미래의 거시적 추세를 추정하는 참고용 회귀 모델입니다.
- **주요 로직 및 알고리즘**:
  - 2025년 6월 이후 최신 데이터를 대상으로 일별 논문 수의 7일 이동평균 수치를 생성합니다.
  - 날짜 경과일(`day_num`) 단일 특징을 기반으로 `PolynomialFeatures(degree=2)`를 사용해 2차 다항 곡선 피팅을 진행합니다.
  - 2차 다항식을 학습한 선형회귀 모델로 2026년 5월 한 달간의 논문 발행 추세를 예측하고 음수 값을 0으로 바운딩(Bounding) 보정합니다.

### src/analysis/forecast_trend_class_models.py (외삽 한계 시각화 및 검증 모듈)
- **개요**: 수업 시간에 다룬 분류용 알고리즘들의 회귀 버전(Regressor)을 시계열 미래 시점(5월)에 적용하여 외삽(Extrapolation) 능력의 부재를 교육적 목적으로 입증합니다.
- **주요 로직 및 알고리즘**:
  - `DecisionTreeRegressor(max_depth=5)`, `KNeighborsRegressor(n_neighbors=7)`, `AdaBoostRegressor` 모델을 학습시킵니다.
  - 과거 학습 영역의 예측 곡선은 잘 피팅하나, 학습 범위를 넘어서는 2026년 5월 예측 영역에 진입하면 예측선들이 상승 추세를 쫓지 못하고 수평으로 뻗어버리는 **Flatline(외삽 실패)** 현상을 좌표 상에 구현하여 플롯으로 저장합니다.
