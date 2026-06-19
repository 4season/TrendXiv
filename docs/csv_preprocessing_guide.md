# Go 언어 CSV 읽기 및 데이터 전처리 라이브러리 가이드

Go 언어에서 CSV 파일을 효율적으로 읽고, 정제(Cleaning)하고, 전처리(Preprocessing)하기 위해 가장 널리 쓰이고 유용한 3가지 방법을 소개합니다.

1. **Gota (`github.com/go-gota/gota/dataframe`)** - **"Go의 Pandas"** (데이터 분석 및 프레임워크 기반 전처리)
2. **csvutil (`github.com/jszwec/csvutil`)** - **"구조체 기반 고성능 매핑"** (정형 데이터 전처리 및 타입 안전성 확보)
3. **Go 표준 라이브러리 (`encoding/csv`)** - **"제로 의존성 및 초고성능"** (메모리 최적화 및 대용량 단순 처리)

---

## 1. Gota (`github.com/go-gota/gota`)

### 특징 및 장점
* **Pandas 스타일의 API**: Python의 Pandas나 R의 data.frame과 유사한 DataFrame, Series 개념을 Go로 이식했습니다.
* **손쉬운 데이터 조작**: 필터링, 컬럼 선택, 정렬, 병합(Join), 그룹화(Group By) 등을 직관적인 메서드 체이닝으로 처리할 수 있습니다.
* **내장 CSV 지원**: `dataframe.ReadCSV` 및 `WriteCSV` 메서드로 간단하게 데이터를 입출력할 수 있습니다.

### 추천 시나리오
* 결측값 제거, 조건부 행 필터링, 컬럼 데이터 타입 변경 등 복잡한 데이터 정제 작업이 필요한 경우
* 여러 개의 CSV 파일을 특정 Key 기준으로 조인(Join)해야 하는 경우

### 설치 방법
```bash
go get github.com/go-gota/gota/dataframe
```

### 전처리 예제 코드
```go
package main

import (
	"fmt"
	"os"
	"strings"

	"github.com/go-gota/gota/dataframe"
	"github.com/go-gota/gota/series"
)

func main() {
	// 1. 임시 CSV 데이터 생성 (실제 파일의 경우 os.Open 사용)
	csvData := `id,title,doi,citation_count,published_year
1,Deep Learning for NLP,10.1002/nlp.1,120,2021
2,Transformer Models Overview,,85,2022
3,Introduction to Go lang,10.1145/go.1,NaN,2020
4,Advanced Neural Networks,10.1002/nn.5,350,2019`

	// 2. CSV 데이터로부터 DataFrame 읽기
	df := dataframe.ReadCSV(strings.NewReader(csvData))
	fmt.Println("--- 원본 데이터 ---")
	fmt.Println(df)

	// 3. 전처리 작업 진행

	// 3-1. 결측치(NaN/빈 문자열) 처리: DOI가 비어있는 행 필터링 (Drop NaN)
	// Filter 기능을 이용해 doi 열이 비어있지 않은(not null) 행만 추출
	cleanedDf := df.Filter(dataframe.F{
		Colname:  "doi",
		Comparator: series.Neq,
		Comparand:  "",
	})

	// 3-2. 결측치 채우기: citation_count가 NaN인 값을 0으로 대체
	// Series 조작을 통해 특정 열의 값을 전처리
	citations := cleanedDf.Col("citation_count")
	for i := 0; i < citations.Len(); i++ {
		val := citations.Val(i)
		if fmt.Sprintf("%v", val) == "NaN" || val == nil {
			citations.Set(i, 0)
		}
	}

	// 3-3. 파생 변수(신규 열) 추가: citation_count가 100 이상이면 "High Impact" 컬럼을 True로 설정
	isHighImpact := make([]bool, cleanedDf.Nrow())
	for i := 0; i < cleanedDf.Nrow(); i++ {
		// 해당 행의 citation_count 값을 int로 받아 판별
		cnt, err := cleanedDf.Elem(i, 3).Int()
		if err == nil && cnt >= 100 {
			isHighImpact[i] = true
		} else {
			isHighImpact[i] = false
		}
	}
	// 새로운 Series를 컬럼으로 추가
	processedDf := cleanedDf.Mutate(series.New(isHighImpact, series.Bool, "high_impact"))

	// 3-4. 특정 컬럼만 선택 및 정렬 (citation_count 기준 내림차순)
	finalDf := processedDf.Select([]string{"id", "title", "doi", "citation_count", "high_impact"}).
		Arrange(dataframe.RevSort("citation_count"))

	fmt.Println("\n--- 전처리 후 데이터 ---")
	fmt.Println(finalDf)

	// 4. 전처리된 결과를 새로운 CSV 파일로 저장
	outFile, err := os.Create("processed_gota.csv")
	if err != nil {
		panic(err)
	}
	defer outFile.Close()

	err = finalDf.WriteCSV(outFile)
	if err != nil {
		panic(err)
	}
	fmt.Println("전처리 완료 후 processed_gota.csv 파일로 저장되었습니다.")
}
```

---

## 2. csvutil (`github.com/jszwec/csvutil`)

### 특징 및 장점
* **타입 안전성(Type Safety)**: Go의 구조체(struct) 태그(`csv:"header_name"`)를 사용하여 CSV 데이터를 강력한 타입의 Go 객체 슬라이스로 즉시 역직렬화(Unmarshal) 및 직렬화(Marshal)합니다.
* **훌륭한 성능**: 반사(Reflection)를 효율적으로 캐싱하여 표준 라이브러리 버금가는 빠른 속도를 보여줍니다.
* **유연한 커스텀 타입 처리**: `csvutil.Marshaler` 및 `Unmarshaler` 인터페이스를 구현하여 날짜 형식 포맷팅이나 커스텀 전처리 로직을 매핑 단계에서 직접 커스텀할 수 있습니다.

### 추천 시나리오
* CSV 데이터의 컬럼 포맷이 고정되어 있고, 비즈니스 로직(Go 구조체 메서드)을 활용한 안전한 전처리를 수행하고자 할 때
* 숫자가 문자열 형태로 되어 있는 등 데이터 구조가 명확할 때 구조체 필드로 바인딩하여 유효성 검사(Validation)를 수행할 때

### 설치 방법
```bash
go get github.com/jszwec/csvutil
```

### 전처리 예제 코드
```go
package main

import (
	"encoding/csv"
	"fmt"
	"io"
	"os"
	"strconv"
	"strings"

	"github.com/jszwec/csvutil"
)

// Paper 구조체 정의 및 csv 태그 매핑
type Paper struct {
	ID            int     `csv:"id"`
	Title         string  `csv:"title"`
	DOI           string  `csv:"doi"`
	CitationCount string  `csv:"citation_count"` // 전처리를 위해 우선 string으로 받음
	PublishedYear int     `csv:"published_year"`
	
	// 파생 변수 (CSV에는 저장되나 읽을 때는 생략 가능)
	IsAcademic    bool    `csv:"is_academic"`
	CitationsClean int    `csv:"citations_clean"`
}

func main() {
	csvData := `id,title,doi,citation_count,published_year
1,Deep Learning for NLP,10.1002/nlp.1,120,2021
2,Transformer Models Overview,,85,2022
3,Introduction to Go lang,10.1145/go.1,NaN,2020`

	// 1. 역직렬화 (CSV -> Struct Slice)
	var papers []Paper
	dec, err := csvutil.NewDecoder(csv.NewReader(strings.NewReader(csvData)))
	if err != nil {
		panic(err)
	}

	for {
		var p Paper
		if err := dec.Decode(&p); err == io.EOF {
			break
		} else if err != nil {
			panic(err)
		}
		papers = append(papers, p)
	}

	fmt.Println("--- 원본 데이터 구조체 목록 ---")
	for _, p := range papers {
		fmt.Printf("%+v\n", p)
	}

	// 2. 구조체 데이터를 순회하며 데이터 정제 및 유효성 검사 수행
	var cleanedPapers []Paper
	for _, p := range papers {
		// 전처리 조건 1: DOI가 없는 데이터는 스킵 (필터링)
		if strings.TrimSpace(p.DOI) == "" {
			continue
		}

		// 전처리 조건 2: CitationCount 파싱 및 결측치(NaN) 처리
		cleanVal := 0
		if p.CitationCount != "NaN" && p.CitationCount != "" {
			parsed, err := strconv.Atoi(p.CitationCount)
			if err == nil {
				cleanVal = parsed
			}
		}
		p.CitationsClean = cleanVal

		// 전처리 조건 3: 신규 변수 계산
		if strings.Contains(strings.ToLower(p.Title), "nlp") || strings.Contains(strings.ToLower(p.Title), "deep") {
			p.IsAcademic = true
		}

		cleanedPapers = append(cleanedPapers, p)
	}

	fmt.Println("\n--- 전처리 완료 후 구조체 목록 ---")
	for _, p := range cleanedPapers {
		fmt.Printf("%+v\n", p)
	}

	// 3. 직렬화 (Struct Slice -> CSV 파일 저장)
	outFile, err := os.Create("processed_csvutil.csv")
	if err != nil {
		panic(err)
	}
	defer outFile.Close()

	writer := csv.NewWriter(outFile)
	enc := csvutil.NewEncoder(writer)

	for _, p := range cleanedPapers {
		if err := enc.Encode(p); err != nil {
			panic(err)
		}
	}
	writer.Flush()
	fmt.Println("\n전처리된 결과가 processed_csvutil.csv 에 저장되었습니다.")
}
```

---

## 3. Go 표준 라이브러리 (`encoding/csv`)

### 특징 및 장점
* **외부 라이브러리 의존성 제로**: 외부 패키지 설치 없이 Go의 기본 런타임만으로 작동합니다.
* **압도적인 처리 속도 및 저메모리**: 가비지 컬렉터(GC) 부하를 최소화하면서 스트리밍 방식으로 수 GB 단위의 CSV 파일을 라인 단위로 읽고 쓸 수 있습니다.
* **정밀한 튜닝 가능**: 필드 구분자(Comma), 주석 문자(Comment), 레이지 인용부호(LazyQuotes) 등을 아주 쉽게 튜닝하여 비표준 포맷의 CSV 파일도 유연하게 파싱할 수 있습니다.

### 추천 시나리오
* CSV 파일 용량이 수백 MB에서 수 GB에 달하여, 메모리에 데이터를 다 올리지 않고 한 행씩(Line-by-line) 읽어 정제한 뒤 즉시 파일에 써야 할 때 (Streaming Preprocessing)
* 단순한 데이터 포맷 변환이나 불필요 행 제거 등 오버헤드가 적어야 하는 파이프라인 설계 시

### 전처리 예제 코드 (스트리밍 방식)
```go
package main

import (
	"encoding/csv"
	"fmt"
	"io"
	"os"
	"strings"
)

func main() {
	csvData := `id,title,doi,citation_count,published_year
1,Deep Learning for NLP,10.1002/nlp.1,120,2021
2,Transformer Models Overview,,85,2022
3,Introduction to Go lang,10.1145/go.1,NaN,2020`

	reader := csv.NewReader(strings.NewReader(csvData))
	// 비표준 CSV의 경우 아래 옵션 조정 가능
	reader.LazyQuotes = true // 인용구 짝이 안 맞아도 에러를 무시하고 읽음
	
	// 출력을 위해 라이터 세팅
	outFile, err := os.Create("processed_std.csv")
	if err != nil {
		panic(err)
	}
	defer outFile.Close()
	writer := csv.NewWriter(outFile)
	defer writer.Flush()

	// 1. 헤더 처리
	headers, err := reader.Read()
	if err != nil {
		panic(err)
	}
	// 헤더에 새로운 열 추가 (예: processed_flag)
	headers = append(headers, "processed_flag")
	if err := writer.Write(headers); err != nil {
		panic(err)
	}

	fmt.Println("--- 한 행씩 스트리밍 읽기 및 전처리 ---")
	
	// 2. 데이터 레코드 라인바이라인 스트리밍
	for {
		record, err := reader.Read()
		if err == io.EOF {
			break
		}
		if err != nil {
			fmt.Printf("스킵된 잘못된 행: %v\n", err)
			continue
		}

		// record[2] = doi, record[3] = citation_count
		doi := record[2]
		
		// [전처리 1] DOI가 빈 문자열인 행은 즉시 필터링(스킵)
		if doi == "" {
			continue
		}

		// [전처리 2] citation_count가 "NaN" 이면 "0"으로 데이터 클렌징
		if record[3] == "NaN" {
			record[3] = "0"
		}

		// [전처리 3] 파생 변수 컬럼 추가
		record = append(record, "true")

		// 정제 완료된 행을 즉시 디스크에 씀 (메모리 절약)
		if err := writer.Write(record); err != nil {
			panic(err)
		}
		fmt.Printf("정제 및 저장 완료: %v\n", record)
	}

	fmt.Println("\n스트리밍 전처리가 완료되어 processed_std.csv 에 기록되었습니다.")
}
```

---

## 요약: 어떤 라이브러리를 선택해야 할까요?

| 라이브러리 | 사용 목적 | 추천 사용 상황 | 난이도 | 성능 |
| :--- | :--- | :--- | :--- | :--- |
| **Gota** | Pandas 스타일의 다차원 전처리 | 다수의 CSV 조인, 그룹 요약 및 동적 데이터 가공 | 쉬움 (메서드 체이닝) | 보통 (메모리 사용 높음) |
| **csvutil** | 구조체 타입의 강력하고 안전한 맵핑 | 사전에 정의된 데이터 형식을 정확하게 바인딩하여 검사할 때 | 보통 (구조체 설계 필요) | 매우 우수 |
| **encoding/csv** (표준) | 스트리밍 기반의 초고성능 및 무의존성 전처리 | 수 GB 크기의 초대형 CSV 데이터 파이프라인 처리 | 보통 (코드가 다소 길어짐) | 최상 (가장 빠름) |
