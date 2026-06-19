package main

import (
	"bufio"
	"bytes"
	"encoding/csv"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"
)

// CitationInfo stores the DOI and citation count of a paper.
type CitationInfo struct {
	DOI           string `json:"doi"`
	CitationCount int    `json:"citation_count"`
}

// PaperResponse matches the structure of Semantic Scholar batch API response.
type PaperResponse struct {
	PaperID     string `json:"paperId"`
	ExternalIDs struct {
		ArXiv string `json:"ArXiv"`
		DOI   string `json:"DOI"`
	} `json:"externalIds"`
	Title         string `json:"title"`
	CitationCount *int   `json:"citationCount"`
}

const (
	cacheFileName  = "../../outputs/csv/citations_cache.json"
	outputFileName = "../../outputs/csv/arxiv_trends_with_citations.csv"
	batchSize      = 500
)

func main() {
	loadEnv()

	fmt.Println("=========================================================")
	fmt.Println("   Semantic Scholar Citation Merger for arXiv Trends     ")
	fmt.Println("=========================================================")

	cache := loadCache()
	fmt.Printf("[Cache] Loaded %d records from %s\n", len(cache), cacheFileName)

	csvPath := "../../data/arxiv_trends.csv"
	if len(os.Args) > 1 {
		csvPath = os.Args[1]
	}
	fmt.Printf("[CSV] Reading %s...\n", csvPath)
	records, headers, idIdx, err := readCSV(csvPath)
	if err != nil {
		fmt.Printf("[Error] Failed to read CSV: %v\n", err)
		return
	}
	totalRows := len(records)
	fmt.Printf("[CSV] Read successful. Total rows: %d (ID column index: %d)\n", totalRows, idIdx)

	missingIDsMap := make(map[string]bool)
	var missingIDs []string

	for _, row := range records {
		if len(row) <= idIdx {
			continue
		}
		rawID := strings.TrimSpace(row[idIdx])
		if rawID == "" {
			continue
		}
		baseID := stripVersion(rawID)
		
		if _, exists := cache[baseID]; !exists {
			if !missingIDsMap[baseID] {
				missingIDsMap[baseID] = true
				missingIDs = append(missingIDs, baseID)
			}
		}
	}

	totalMissing := len(missingIDs)
	fmt.Printf("[Analysis] %d unique arXiv IDs in CSV. %d need to be fetched from API.\n", 
		len(missingIDsMap)+len(cache)-len(missingIDsMap), totalMissing)

	apiKey := os.Getenv("SEMANTIC_SCHOLAR_API_KEY")
	delayMs := 3000
	
	if apiKey != "" {
		fmt.Println("[Auth] API Key detected. Using strict rate-limited settings (1.2s delay to respect 1 req/sec limit).")
		delayMs = 1200
	} else {
		fmt.Println("[Auth] No API Key detected. Using safe 3.0s delay to prevent rate limit blocks.")
	}

	if envDelay := os.Getenv("SEMANTIC_SCHOLAR_DELAY_MS"); envDelay != "" {
		if val, err := strconv.Atoi(envDelay); err == nil {
			delayMs = val
			fmt.Printf("[Config] Override delay set to %d ms\n", delayMs)
		}
	}

	if delayMs < 1100 {
		fmt.Printf("[Warning] Requested delay %d ms is below the safe threshold of 1 request per second. Overriding to 1200 ms for safety.\n", delayMs)
		delayMs = 1200
	}

	if totalMissing > 0 {
		fmt.Printf("[Fetch] Starting batch processing (Batch Size: %d, Delay: %dms)...\n", batchSize, delayMs)
		startTime := time.Now()
		
		for i := 0; i < totalMissing; i += batchSize {
			end := i + batchSize
			if end > totalMissing {
				end = totalMissing
			}
			chunk := missingIDs[i:end]
			
			fmt.Printf("[Progress] Fetching IDs %d to %d of %d (%.2f%%)...\n", 
				i+1, end, totalMissing, float64(end)/float64(totalMissing)*100)

			results, err := fetchBatchWithRetry(chunk, apiKey)
			if err != nil {
				fmt.Printf("[Error] Failed to fetch batch starting at index %d: %v\n", i, err)
				fmt.Println("[Warning] Saving current cache and exiting. Run the script again to resume.")
				saveCache(cache)
				return
			}

			foundCount := 0
			for _, paper := range results {
				pArXiv := strings.TrimSpace(paper.ExternalIDs.ArXiv)
				if pArXiv == "" {
					continue
				}
				baseArXiv := stripVersion(pArXiv)
				
				citationCount := 0
				if paper.CitationCount != nil {
					citationCount = *paper.CitationCount
				}

				doi := strings.TrimSpace(paper.ExternalIDs.DOI)
				if doi == "" {
					doi = "10.48550/arXiv." + baseArXiv
				}

				cache[baseArXiv] = CitationInfo{
					DOI:           doi,
					CitationCount: citationCount,
				}
				foundCount++
			}

			for _, reqID := range chunk {
				if _, exists := cache[reqID]; !exists {
					cache[reqID] = CitationInfo{
						DOI:           "10.48550/arXiv." + reqID,
						CitationCount: 0,
					}
				}
			}

			fmt.Printf("[Batch Result] Fetched %d papers. Found %d active metadata mappings.\n", len(chunk), foundCount)

			saveCache(cache)

			if end < totalMissing {
				time.Sleep(time.Duration(delayMs) * time.Millisecond)
			}
		}

		elapsed := time.Since(startTime)
		fmt.Printf("[Fetch] API fetching complete! Elapsed time: %v\n", elapsed)
	} else {
		fmt.Println("[Fetch] All required records are already in cache. Skipping API phase.")
	}

	fmt.Printf("[CSV] Writing combined data to %s...\n", outputFileName)
	err = writeCombinedCSV(csvPath, headers, records, idIdx, cache)
	if err != nil {
		fmt.Printf("[Error] Failed to write combined CSV: %v\n", err)
		return
	}

	fmt.Println("\n=========================================================")
	fmt.Println("   Process Completed Successfully!                       ")
	fmt.Printf("   Combined CSV: %s\n", outputFileName)
	fmt.Printf("   Cache Database: %s (%d records)\n", cacheFileName, len(cache))
	fmt.Println("=========================================================")
}

func stripVersion(id string) string {
	parts := strings.Split(id, "v")
	if len(parts) > 0 {
		return parts[0]
	}
	return id
}

func loadCache() map[string]CitationInfo {
	cache := make(map[string]CitationInfo)
	if _, err := os.Stat(cacheFileName); os.IsNotExist(err) {
		return cache
	}

	file, err := os.Open(cacheFileName)
	if err != nil {
		fmt.Printf("[Cache Warning] Could not open cache file: %v. Starting fresh.\n", err)
		return cache
	}
	defer file.Close()

	decoder := json.NewDecoder(file)
	if err := decoder.Decode(&cache); err != nil {
		fmt.Printf("[Cache Warning] Failed to parse cache: %v. Starting fresh.\n", err)
		return make(map[string]CitationInfo)
	}

	return cache
}

func saveCache(cache map[string]CitationInfo) {
	tempFile := cacheFileName + ".tmp"
	file, err := os.Create(tempFile)
	if err != nil {
		fmt.Printf("[Cache Error] Failed to create temp cache file: %v\n", err)
		return
	}

	encoder := json.NewEncoder(file)
	encoder.SetIndent("", "  ")
	if err := encoder.Encode(cache); err != nil {
		file.Close()
		fmt.Printf("[Cache Error] Failed to encode cache: %v\n", err)
		return
	}
	file.Close()

	if err := os.Rename(tempFile, cacheFileName); err != nil {
		fmt.Printf("[Cache Error] Failed to save cache: %v\n", err)
	}
}

func readCSV(path string) ([][]string, []string, int, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, nil, -1, err
	}
	defer file.Close()

	reader := csv.NewReader(file)
	reader.LazyQuotes = true

	headers, err := reader.Read()
	if err != nil {
		return nil, nil, -1, fmt.Errorf("failed to read CSV header: %w", err)
	}

	idIdx := -1
	for idx, h := range headers {
		if strings.ToUpper(h) == "ID" {
			idIdx = idx
			break
		}
	}

	if idIdx == -1 {
		return nil, nil, -1, fmt.Errorf("could not find 'ID' column in CSV headers: %v", headers)
	}

	var records [][]string
	for {
		record, err := reader.Read()
		if err == io.EOF {
			break
		}
		if err != nil {
			continue
		}
		records = append(records, record)
	}

	return records, headers, idIdx, nil
}

func fetchBatchWithRetry(arxivIDs []string, apiKey string) ([]PaperResponse, error) {
	apiIDs := make([]string, len(arxivIDs))
	for i, id := range arxivIDs {
		apiIDs[i] = "ARXIV:" + id
	}

	payload := map[string][]string{
		"ids": apiIDs,
	}

	jsonPayload, err := json.Marshal(payload)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal payload: %w", err)
	}

	url := "https://api.semanticscholar.org/graph/v1/paper/batch?fields=externalIds,citationCount,title"
	
	maxRetries := 5
	baseBackoff := 2.0

	for attempt := 1; attempt <= maxRetries; attempt++ {
		req, err := http.NewRequest("POST", url, bytes.NewBuffer(jsonPayload))
		if err != nil {
			return nil, fmt.Errorf("failed to create HTTP request: %w", err)
		}
		req.Header.Set("Content-Type", "application/json")
		if apiKey != "" {
			req.Header.Set("x-api-key", apiKey)
		}

		client := &http.Client{
			Timeout: 30 * time.Second,
		}

		resp, err := client.Do(req)
		if err != nil {
			fmt.Printf("  [Attempt %d/%d] Network error: %v. Retrying in %v...\n", 
				attempt, maxRetries, err, time.Duration(baseBackoff)*time.Second)
			time.Sleep(time.Duration(baseBackoff) * time.Second)
			baseBackoff *= 2.0
			continue
		}

		if resp.StatusCode == 429 || (resp.StatusCode >= 500 && resp.StatusCode <= 599) {
			resp.Body.Close()
			backoffDuration := time.Duration(baseBackoff) * time.Second
			if resp.StatusCode == 429 {
				fmt.Printf("  [Attempt %d/%d] HTTP 429 Too Many Requests. Increasing backoff. Retrying in %v...\n", 
					attempt, maxRetries, backoffDuration)
			} else {
				fmt.Printf("  [Attempt %d/%d] HTTP %d Server Error. Retrying in %v...\n", 
					attempt, maxRetries, resp.StatusCode, backoffDuration)
			}
			time.Sleep(backoffDuration)
			baseBackoff *= 2.0
			continue
		}

		if resp.StatusCode != http.StatusOK {
			respBytes, _ := io.ReadAll(resp.Body)
			resp.Body.Close()
			return nil, fmt.Errorf("API request failed with status %s: %s", resp.Status, string(respBytes))
		}

		var papers []PaperResponse
		decoder := json.NewDecoder(resp.Body)
		if err := decoder.Decode(&papers); err != nil {
			resp.Body.Close()
			return nil, fmt.Errorf("failed to decode response JSON: %w", err)
		}
		resp.Body.Close()

		return papers, nil
	}

	return nil, fmt.Errorf("API request failed after %d attempts", maxRetries)
}

func writeCombinedCSV(originalPath string, headers []string, records [][]string, idIdx int, cache map[string]CitationInfo) error {
	outFile, err := os.Create(outputFileName)
	if err != nil {
		return err
	}
	defer outFile.Close()

	writer := csv.NewWriter(outFile)
	defer writer.Flush()

	newHeaders := make([]string, len(headers))
	copy(newHeaders, headers)
	newHeaders = append(newHeaders, "DOI", "CitationCount")

	if err := writer.Write(newHeaders); err != nil {
		return fmt.Errorf("failed to write header to output CSV: %w", err)
	}

	for idx, row := range records {
		var doi string
		citationCountStr := "0"

		if len(row) > idIdx {
			rawID := strings.TrimSpace(row[idIdx])
			baseID := stripVersion(rawID)
			
			if info, exists := cache[baseID]; exists {
				doi = info.DOI
				citationCountStr = strconv.Itoa(info.CitationCount)
			} else {
				doi = "10.48550/arXiv." + baseID
				citationCountStr = "0"
			}
		}

		newRow := make([]string, len(row))
		copy(newRow, row)
		newRow = append(newRow, doi, citationCountStr)

		if err := writer.Write(newRow); err != nil {
			return fmt.Errorf("failed to write row %d to output CSV: %w", idx, err)
		}
	}

	return nil
}

func loadEnv() {
	file, err := os.Open(".env")
	if err != nil {
		return
	}
	defer file.Close()

	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}

		var key, value string
		if idx := strings.Index(line, "="); idx != -1 {
			key = strings.TrimSpace(line[:idx])
			value = strings.TrimSpace(line[idx+1:])
		} else if idx := strings.Index(line, ":"); idx != -1 {
			key = strings.TrimSpace(line[:idx])
			value = strings.TrimSpace(line[idx+1:])
		} else {
			continue
		}

		value = strings.Trim(value, `"'`)

		if key != "" {
			os.Setenv(key, value)
		}
	}
}

