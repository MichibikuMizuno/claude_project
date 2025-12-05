"""
弁護士ドットコム 検索結果スクレイピング サンプルコード（高速版）
"""

import os
import csv
import time
import re
import json
import concurrent.futures
from typing import List, Tuple

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException

import requests
from bs4 import BeautifulSoup

# =============================================================================
# 設定値
# =============================================================================

OUTPUT_CSV = "lawyers.csv"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
MAX_WORKERS = 10  # 並列リクエスト数

# 都道府県コード
PREF_URL_MAP = {
    "北海道": "hokkaido", "青森県": "aomori", "岩手県": "iwate", "宮城県": "miyagi",
    "秋田県": "akita", "山形県": "yamagata", "福島県": "fukushima", "茨城県": "ibaraki",
    "栃木県": "tochigi", "群馬県": "gunma", "埼玉県": "saitama", "千葉県": "chiba",
    "東京都": "tokyo", "神奈川県": "kanagawa", "新潟県": "niigata", "富山県": "toyama",
    "石川県": "ishikawa", "福井県": "fukui", "山梨県": "yamanashi", "長野県": "nagano",
    "岐阜県": "gifu", "静岡県": "shizuoka", "愛知県": "aichi", "三重県": "mie",
    "滋賀県": "shiga", "京都府": "kyoto", "大阪府": "osaka", "兵庫県": "hyogo",
    "奈良県": "nara", "和歌山県": "wakayama", "鳥取県": "tottori", "島根県": "shimane",
    "岡山県": "okayama", "広島県": "hiroshima", "山口県": "yamaguchi", "徳島県": "tokushima",
    "香川県": "kagawa", "愛媛県": "ehime", "高知県": "kochi", "福岡県": "fukuoka",
    "佐賀県": "saga", "長崎県": "nagasaki", "熊本県": "kumamoto", "大分県": "oita",
    "宮崎県": "miyazaki", "鹿児島県": "kagoshima", "沖縄県": "okinawa",
}

# 市区町村コード（a_XXXXX形式）
CITY_CODE_MAP = {
    # 東京都
    "千代田区": "13101", "中央区": "13102", "港区": "13103", "新宿区": "13104",
    "文京区": "13105", "台東区": "13106", "墨田区": "13107", "江東区": "13108",
    "品川区": "13109", "目黒区": "13110", "大田区": "13111", "世田谷区": "13112",
    "渋谷区": "13113", "中野区": "13114", "杉並区": "13115", "豊島区": "13116",
    "北区": "13117", "荒川区": "13118", "板橋区": "13119", "練馬区": "13120",
    "足立区": "13121", "葛飾区": "13122", "江戸川区": "13123",
    "八王子市": "13201", "立川市": "13202", "武蔵野市": "13203", "三鷹市": "13204",
    "府中市": "13206", "調布市": "13208", "町田市": "13209", "小金井市": "13210",
    # 大阪府
    "大阪市": "27100", "堺市": "27140", "豊中市": "27203", "吹田市": "27205",
    "高槻市": "27207", "枚方市": "27210", "茨木市": "27211", "八尾市": "27212",
    # 神奈川県
    "横浜市": "14100", "川崎市": "14130", "相模原市": "14150", "横須賀市": "14201",
    "藤沢市": "14205", "小田原市": "14206", "厚木市": "14212",
    # 愛知県
    "名古屋市": "23100", "豊橋市": "23201", "岡崎市": "23202", "一宮市": "23203",
    "豊田市": "23211",
    # 埼玉県
    "さいたま市": "11100", "川越市": "11201", "川口市": "11203", "所沢市": "11208",
    "越谷市": "11222",
    # 千葉県
    "千葉市": "12100", "市川市": "12203", "船橋市": "12204", "松戸市": "12207",
    "柏市": "12217",
    # 福岡県
    "北九州市": "40100", "福岡市": "40130",
    # 兵庫県
    "神戸市": "28100", "姫路市": "28201", "尼崎市": "28202", "西宮市": "28204",
}

# 相談カテゴリコード（f_X形式）
CATEGORY_CODE_MAP = {
    "離婚・男女問題": "3",
    "相続": "9",
    "労働問題": "5",
    "交通事故": "2",
    "債務整理": "1",
    "借金": "1",
    "刑事事件": "6",
    "犯罪・刑事事件": "6",
    "不動産・建築": "8",
    "企業法務": "14",
    "消費者被害": "11",
    "インターネット": "13",
    "債権回収": "4",
}


def get_env_variables() -> Tuple[str, str, str]:
    """環境変数から検索条件を取得"""
    pref = os.getenv("PREF_NAME")
    city = os.getenv("CITY_NAME")
    category = os.getenv("CATEGORY_NAME")

    if not all([pref, city, category]):
        missing = [k for k, v in [("PREF_NAME", pref), ("CITY_NAME", city), ("CATEGORY_NAME", category)] if not v]
        raise ValueError(f"環境変数未設定: {', '.join(missing)}")

    return pref, city, category


def setup_driver() -> webdriver.Chrome:
    """高速設定のWebDriver"""
    options = webdriver.ChromeOptions()
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--blink-settings=imagesEnabled=false")
    options.page_load_strategy = 'eager'

    driver = webdriver.Chrome(options=options)
    driver.implicitly_wait(2)
    return driver


def build_search_url(pref: str, city: str, category: str) -> str:
    """検索結果ページのURLを構築"""
    pref_path = PREF_URL_MAP.get(pref)
    city_code = CITY_CODE_MAP.get(city)
    category_code = CATEGORY_CODE_MAP.get(category)

    if not pref_path:
        raise ValueError(f"都道府県 '{pref}' が見つかりません")

    # URLパターン: /tokyo/a_13104/f_3/ (都道府県/a_市区町村コード/f_分野コード)
    url = f"https://www.bengo4.com/{pref_path}/"

    if city_code:
        url += f"a_{city_code}/"

    if category_code:
        url += f"f_{category_code}/"

    return url


def extract_urls_fast(driver: webdriver.Chrome, max_pages: int = 3) -> List[str]:
    """高速URL抽出"""
    all_urls = set()
    base_url = driver.current_url.split('?')[0]

    for page in range(1, max_pages + 1):
        print(f"ページ {page} 処理中...")

        # JavaScriptで弁護士リンクを一括取得
        # /l_XXXX/ パターンで、不要なページを除外し、プロフィールページのみ取得
        urls = driver.execute_script("""
            return Array.from(document.querySelectorAll('a[href*="/l_"]'))
                .map(a => a.href.split('?')[0].split('#')[0])
                .filter(url => {
                    if (!url.includes('/l_')) return false;
                    // 除外パターン
                    if (url.includes('/contact')) return false;
                    if (url.includes('/case/')) return false;
                    if (url.includes('/column/')) return false;
                    if (url.includes('/qa/')) return false;
                    if (url.includes('/review/')) return false;
                    // /l_XXXXX/ で終わるURLのみ（弁護士ID直後で終わる）
                    return url.match(/\/l_\d+\/?$/);
                })
                .map(url => url.endsWith('/') ? url : url + '/')
                .filter((url, i, arr) => arr.indexOf(url) === i);
        """)

        # Python側でも再フィルタリング（確実に除外）
        clean_urls = []
        for url in urls:
            # /l_数字/ で終わるURLのみ許可
            if re.search(r'/l_\d+/$', url):
                # 除外パターンがないことを確認
                if not any(x in url for x in ['/contact', '/case/', '/column/', '/qa/', '/review/']):
                    clean_urls.append(url)

        before_count = len(all_urls)
        all_urls.update(clean_urls)
        new_count = len(all_urls) - before_count
        print(f"  {new_count}件取得 (累計: {len(all_urls)}件)")

        # 次ページへ
        if page < max_pages:
            next_page = page + 1
            next_url = f"{base_url}?page={next_page}"
            try:
                driver.get(next_url)
                # ページが存在しない場合（リダイレクトされた場合）は終了
                if f"page={next_page}" not in driver.current_url and "page=" not in driver.current_url:
                    if page > 1:  # 1ページ目以降で
                        print("  最終ページ到達")
                        break
            except Exception:
                break

    return list(all_urls)


def fetch_lawyer_name_fast(url: str) -> Tuple[str, str]:
    """高速で弁護士名を取得（並列処理用）"""
    try:
        response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=5)
        soup = BeautifulSoup(response.text, "html.parser")

        # 方法1: JSON-LDから取得（最も正確）
        scripts = soup.find_all("script", {"type": "application/ld+json"})
        for script in scripts:
            try:
                data = json.loads(script.string)
                if isinstance(data, dict) and data.get("name"):
                    name = data["name"]
                    if len(name) < 20:
                        return (url, name)
            except:
                pass

        # 方法2: og:titleから取得（「名前弁護士（事務所）」形式）
        meta = soup.find("meta", {"property": "og:title"})
        if meta:
            content = meta.get("content", "")
            # 「野島 梨恵弁護士（新都心法律事務所）」から「野島 梨恵」を抽出
            if "弁護士" in content:
                name = content.split("弁護士")[0].strip()
                if name and len(name) < 20:
                    return (url, name)

        return (url, "")
    except Exception:
        return (url, "")


def fetch_all_names_parallel(urls: List[str]) -> dict:
    """並列で全弁護士名を取得"""
    print(f"\n{len(urls)}件の弁護士情報を並列取得中...")

    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(fetch_lawyer_name_fast, url): url for url in urls}

        for future in concurrent.futures.as_completed(futures):
            url, name = future.result()
            results[url] = name

    return results


def save_csv(data: List[Tuple], filename: str = OUTPUT_CSV):
    """CSV保存"""
    with open(filename, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["prefecture", "city", "category", "lawyer_name", "profile_url"])
        writer.writerows(data)
    print(f"\n{len(data)}件を {filename} に保存")


def main():
    start_time = time.time()
    print("=" * 50)
    print("弁護士ドットコム スクレイピング（高速版）")
    print("=" * 50)

    driver = None
    try:
        pref, city, category = get_env_variables()
        print(f"検索: {pref} / {city} / {category}")

        # 検索URLを構築
        search_url = build_search_url(pref, city, category)
        print(f"アクセス: {search_url}")

        driver = setup_driver()
        driver.get(search_url)

        # URL収集（ページ数を増やして多く取得）
        urls = extract_urls_fast(driver, max_pages=10)
        print(f"\n合計 {len(urls)} 件のURL取得")

        if not urls:
            print("URLが取得できませんでした")
            print("ページ内容を確認:")
            print(driver.current_url)
            return

        # 並列で弁護士名取得
        names = fetch_all_names_parallel(urls)

        # 結果作成
        results = []
        for url in urls:
            name = names.get(url, "")
            results.append((pref, city, category, name or "(取得失敗)", url))

        # CSV保存
        save_csv(results)

        elapsed = time.time() - start_time
        print(f"\n完了！ 処理時間: {elapsed:.1f}秒")

    except ValueError as e:
        print(f"エラー: {e}")
    except Exception as e:
        print(f"エラー: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if driver:
            driver.quit()


if __name__ == "__main__":
    main()
