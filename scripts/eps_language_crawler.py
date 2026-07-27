import csv
import json
import re
import time
from typing import List, Dict
from curl_cffi import requests
from bs4 import BeautifulSoup

# EPS 한국산업인력공단 외국어 DB 수집 크롤러
BASE_URL = "https://eps.hrdkorea.or.kr/e9/user/language/language.do"

LANGUAGES = {
    "01": "영어 (English)",
    "02": "중국어 (Chinese)",
    "03": "베트남어 (Vietnamese)",
    "04": "태국어 (Thai)",
    "05": "따갈로그어 (Tagalog)",
    "06": "인도네시아어 (Bahasa Indonesia)",
    "07": "몽골어 (Mongolian)",
    "08": "스리랑카어 (Sri Lanka)",
    "09": "러시아어 (Russian)",
    "10": "우즈벡어 (Uzbekistan)",
    "11": "키르키즈어 (Kyrgyzstan)",
    "13": "방글라데시어 (Bangla)",
    "14": "파키스탄어 (Urdu)",
    "15": "캄보디아어 (Cambodian)",
    "17": "동티모르어 (Timor-Leste)",
}

def get_max_page(session: requests.Session, lang_code: str) -> int:
    """해당 언어 카테고리의 전체 페이지 수를 확인합니다."""
    payload = {
        "method": "languageSearch",
        "searchLanguage": lang_code,
        "currentPage": "1"
    }
    try:
        res = session.post(BASE_URL, data=payload, impersonate="safari", timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")
        pages = [1]
        for a in soup.find_all("a", href=True):
            m = re.search(r"movePage\((\d+)\)", a["href"])
            if m:
                pages.append(int(m.group(1)))
        return max(pages)
    except Exception as e:
        print(f"[!] 최대 페이지 확인 실패 ({lang_code}): {e}")
        return 1

def fetch_language_page(session: requests.Session, lang_code: str, page: int) -> List[Dict[str, str]]:
    """단일 페이지의 단어, 외국어 표현, 한국어 발음을 분리하여 수집합니다."""
    payload = {
        "method": "languageSearch",
        "searchLanguage": lang_code,
        "currentPage": str(page)
    }
    items = []
    try:
        res = session.post(BASE_URL, data=payload, impersonate="safari", timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")
        
        tables = soup.find_all("table")
        if len(tables) < 2:
            return items
        
        target_table = tables[1]
        rows = target_table.find_all("tr")[1:] # 헤더 제외
        
        for r in rows:
            tds = r.find_all("td")
            if len(tds) >= 2:
                korean = tds[0].text.strip()
                target_td = tds[1]
                
                # <span> 태그 안에 한국어 발음이 있음
                span = target_td.find("span")
                if span:
                    pronunciation = span.text.strip()
                    span.extract() # span 분리
                else:
                    pronunciation = ""
                
                foreign_text = target_td.text.strip()
                
                items.append({
                    "lang_code": lang_code,
                    "lang_name": LANGUAGES.get(lang_code, lang_code),
                    "page": page,
                    "korean": korean,
                    "foreign_translation": foreign_text,
                    "pronunciation": pronunciation
                })
    except Exception as e:
        print(f"[!] 페이지 수집 에러 ({lang_code} p.{page}): {e}")
    
    return items

def crawl_all(target_languages: List[str] = None, max_pages_limit: int = None):
    """지정한 언어(기본값: 전체)에 대해 데이터를 수집합니다."""
    session = requests.Session()
    all_data = []
    codes = target_languages if target_languages else list(LANGUAGES.keys())
    
    print("=" * 60)
    print("EPS 한국산업인력공단 다국어 회화/용어 DB 수집 (외국어 & 한국어 발음 분리)")
    print("=" * 60)

    for code in codes:
        lang_name = LANGUAGES.get(code, code)
        max_page = get_max_page(session, code)
        if max_pages_limit:
            max_page = min(max_page, max_pages_limit)

        print(f"\n[+] [{lang_name}] 총 {max_page} 페이지 수집 중...")
        lang_count = 0
        for p in range(1, max_page + 1):
            items = fetch_language_page(session, code, p)
            all_data.extend(items)
            lang_count += len(items)
            print(f"  └- {p}/{max_page} 페이지 완료 ({len(items)}건)", end="\r")
            time.sleep(0.1)
            
        print(f"\n  ✔ {lang_name} 수집 완료: 총 {lang_count}건")

    # JSON 저장
    json_path = "eps_language_db.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)
    print(f"\n[★] JSON 저장 완료: {json_path} (총 {len(all_data)}건)")

    # CSV 저장
    csv_path = "eps_language_db.csv"
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["lang_code", "lang_name", "page", "korean", "foreign_translation", "pronunciation"])
        writer.writeheader()
        writer.writerows(all_data)
    print(f"[★] CSV 저장 완료: {csv_path}")

if __name__ == "__main__":
    import sys
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    crawl_all(max_pages_limit=limit)
