import requests
import xml.etree.ElementTree as ET
import time
import csv
import os
import re

def batch_to_csv(batch_data, filename="arxiv_trends.csv"):

    base_dir = os.path.dirname(os.path.abspath(__file__))
    target_dir = os.path.join(base_dir, "..", "..", "data")
    os.makedirs(target_dir, exist_ok=True)

    full_path = os.path.join(target_dir, filename)
    file_exists = os.path.isfile(full_path)

    with open(full_path, 'a', encoding='utf-8-sig', newline='') as file:
        writer = csv.writer(file)
        if not file_exists:
            writer.writerow(['Identifier', 'Datestamp', 'SetSpecs', 'ID', 'Created', 'Updated', 'Title', 'Category', 'Abstract'])
        
        writer.writerows(batch_data)

def fetch_arxiv_trends_data():
    base_url = "https://oaipmh.arxiv.org/oai"
    params = {
        'verb': 'ListRecords',
        'metadataPrefix': 'arXiv',
        'set': 'cs',
        'from': '2026-01-01',
        'until': '2026-04-30'
    }
    
    namespaces = {
        'oai': 'http://www.openarchives.org/OAI/2.0/'
    }

    total_records_processed = 0

    while True:
        try:
            print(f"데이터를 요청 중입니다... (파라미터: {params})")
            response = requests.get(base_url, params=params)
            response.raise_for_status()
            
            root = ET.fromstring(response.text)
            records = root.findall('.//oai:record', namespaces)
            
            batch_data_list = []
            
            for record in records:
                header = record.find('oai:header', namespaces)
                if header is None:
                    continue 

                iden_elem = header.find('oai:identifier', namespaces)
                identifier = iden_elem.text.strip() if iden_elem is not None else "No ID"
                
                date_elem = header.find('oai:datestamp', namespaces)
                datestamp = date_elem.text.strip() if date_elem is not None else "No DateStamp"
                
                set_elems = header.findall('oai:setSpec', namespaces)
                setSpecs = [set_elem.text for set_elem in set_elems if set_elem.text is not None]
                sets_to_string = "|".join(setSpecs)

                metadata_container = record.find('oai:metadata', namespaces)
                if metadata_container is None or len(metadata_container) == 0:
                    continue

                metadata = list(metadata_container)[0]

                match = re.match(r'\{(.*)\}', metadata.tag)
                ns_uri = match.group(1) if match else ''

                def get_text(tag_name):
                    elem = metadata.find(f'{{{ns_uri}}}{tag_name}')
                    if elem is not None and elem.text:
                        return elem.text.replace('\n', ' ').strip()
                    return f"No {tag_name.capitalize()}"

                paper_id = get_text('id')
                title = get_text('title')
                created = get_text('created')
                updated = get_text('updated')
                abstract = get_text('abstract')
                category = get_text('categories') 

                batch_data_list.append([identifier, datestamp, sets_to_string, paper_id, created, updated, title, category, abstract])
                total_records_processed += 1

            if batch_data_list:
                batch_to_csv(batch_data_list)
                print(f"✅ 현재 배치 저장 완료! (누적 수집량: {total_records_processed}건)")
            else:
                print("⚠️ 이번 페이지의 논문들은 모두 삭제된 상태이거나 유효한 정보가 없습니다.")

            token_element = root.find('.//oai:resumptionToken', namespaces)
            
            if token_element is None or not token_element.text:
                print("더 이상 가져올 데이터가 없습니다. 전체 수집 완료!")
                break
            
            params = {
                'verb': 'ListRecords',
                'resumptionToken': token_element.text
            }
            
            print("서버 배려를 위해 5초 대기합니다... ⏳")
            time.sleep(5)

        except requests.exceptions.HTTPError as e:
            print(f"네트워크 에러 발생: {e}. 30초 후 다시 시도합니다.")
            time.sleep(30)
            continue
        except ET.ParseError:
            print("XML 파싱 에러 발생. 응답 데이터를 확인하세요.")
            break
        except Exception as e:
            print(f"예상치 못한 에러 발생: {e}")
            break

if __name__ == "__main__":
    fetch_arxiv_trends_data()