import os
import time
import requests
import pandas as pd
import duckdb
from datetime import datetime
from pathlib import Path
import argparse


SCRAPED_COLUMNS = [
    "itemid",
    "shopid",
    "name",
    "price_min",
    "price_max",
    "sold",
    "rating_star",
    "category_id",
    "raw_content",
    "crawl_time",
]

def fetch_tiki_search_items(keyword: str, page_number: int, limit: int = 50) -> dict:
    url = "https://tiki.vn/api/v2/products"
    params = {
        "limit": limit,
        "q": keyword,
        "page": page_number + 1, # API Tiki phân trang bắt đầu từ 1
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
    }
    
    try:
        r = requests.get(url, params=params, headers=headers, timeout=15)
        if r.status_code != 200:
            print(f"[!] Lỗi HTTP khi gọi API Tiki: {r.status_code}")
        return r.json()
    except Exception as e:
        print(f"[!] Lỗi kết nối Tiki: {e}")
        return {}


def fetch_tiki_product_detail(item_id: int) -> dict:
    url = f"https://tiki.vn/api/v2/products/{item_id}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
    }

    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code != 200:
            print(f"[!] Không lấy được chi tiết item {item_id}. HTTP: {r.status_code}")
            return {}
        return r.json()
    except Exception as e:
        print(f"[!] Lỗi khi lấy chi tiết item {item_id}: {e}")
        return {}

def flatten_tiki_item(item: dict) -> dict:
    # Lấy ngắn miêu tả từ thẻ mô tả ngắn (nếu có)
    short_desc = item.get("short_description", "")
    
    return {
        "itemid": item.get("id"),
        "shopid": item.get("seller_product_id") or 0,
        "name": item.get("name"),  # Dữ liệu chính để phân tích văn bản
        "price_min": item.get("price") or item.get("original_price"),
        "price_max": item.get("original_price"),
        "sold": item.get("quantity_sold", {}).get("value", 0),
        "rating_star": item.get("rating_average", 0.0),
        "category_id": item.get("primary_category"),
        "raw_content": short_desc,
        "crawl_time": str(datetime.now())
    }


def flatten_tiki_detail_item(item: dict) -> dict:
    category = item.get("primary_category")
    if isinstance(category, dict):
        category = category.get("id")

    return {
        "itemid": item.get("id"),
        "shopid": item.get("seller_product_id") or 0,
        "name": item.get("name"),
        "price_min": item.get("price") or item.get("original_price"),
        "price_max": item.get("original_price") or item.get("price"),
        "sold": item.get("quantity_sold", {}).get("value", 0),
        "rating_star": item.get("rating_average", 0.0),
        "category_id": category,
        "raw_content": item.get("short_description", ""),
        "crawl_time": str(datetime.now()),
    }


def save_scraped_items(df: pd.DataFrame, output_dir: str, replace_table: bool = True):
    for c in SCRAPED_COLUMNS:
        if c not in df.columns:
            df[c] = None

    df = df[SCRAPED_COLUMNS]

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    db_path = os.path.join(output_dir, "tiki_scraped_data.duckdb")

    con = duckdb.connect(db_path)
    table_exists = con.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'scraped_items'"
    ).fetchone()[0]

    if replace_table or not table_exists:
        con.execute("DROP TABLE IF EXISTS scraped_items")
        con.execute(
            """
            CREATE TABLE scraped_items (
                itemid BIGINT,
                shopid BIGINT,
                name VARCHAR,
                price_min BIGINT,
                price_max BIGINT,
                sold INT,
                rating_star DOUBLE,
                category_id BIGINT,
                raw_content VARCHAR,
                crawl_time VARCHAR
            )
            """
        )
        final_df = df
    else:
        old_df = con.execute("SELECT * FROM scraped_items").fetchdf()
        final_df = pd.concat([old_df, df], ignore_index=True)
        final_df = final_df.drop_duplicates(subset=["itemid"], keep="last")
        con.execute("DROP TABLE IF EXISTS scraped_items")
        con.execute(
            """
            CREATE TABLE scraped_items (
                itemid BIGINT,
                shopid BIGINT,
                name VARCHAR,
                price_min BIGINT,
                price_max BIGINT,
                sold INT,
                rating_star DOUBLE,
                category_id BIGINT,
                raw_content VARCHAR,
                crawl_time VARCHAR
            )
            """
        )

    con.append("scraped_items", final_df)
    con.close()
    return db_path

def scrape_tiki(keyword: str, max_pages: int, output_dir: str):
    print(f"[*] Bắt đầu cào dữ liệu từ Tiki cho từ khóa: '{keyword}'")
    
    all_items = []
    limit = 50 # Tiki khuyến nghị 40-50
    
    for page in range(max_pages):
        print(f"[-] Đang cào trang {page + 1}...")
        
        data = fetch_tiki_search_items(keyword, page, limit)
        items = data.get("data") or []
        
        if not items:
            print("[-] Không còn dữ liệu hoặc bị Tiki giới hạn kết quả.")
            break
            
        for it in items:
            try:
                row = flatten_tiki_item(it)
                all_items.append(row)
            except Exception as e:
                pass
        
        if len(items) < limit:
            break
            
        time.sleep(1.5)  # Delay để không bị block IP

    if not all_items:
        print("[!] Không có dữ liệu nào được cào về từ Tiki.")
        return

    # Lưu dữ liệu ra Dataframe
    df = pd.DataFrame(all_items)
    
    # Loại bỏ dữ liệu trùng lặp
    df = df.drop_duplicates(subset=['itemid'])
    
    db_path = save_scraped_items(df, output_dir, replace_table=False)
    
    print(f"[*] Đã thu thập {len(df)} sản phẩm từ TIKI. Lưu vào DuckDB: {db_path} (Bảng: scraped_items)")
    print("[*] Hoàn tất! Team Data có thể sử dụng file này để test clean text.")


def refresh_existing_tiki_items(output_dir: str, max_items: int | None = None, delay_seconds: float = 0.4):
    db_path = os.path.join(output_dir, "tiki_scraped_data.duckdb")
    if not os.path.exists(db_path):
        print(f"[!] Chưa tìm thấy DB tại: {db_path}")
        return False

    con = duckdb.connect(db_path)
    try:
        exists = con.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'scraped_items'"
        ).fetchone()[0]
        if not exists:
            print("[!] Chưa có bảng scraped_items để refresh.")
            return False

        query = "SELECT DISTINCT itemid FROM scraped_items WHERE itemid IS NOT NULL"
        if max_items and max_items > 0:
            query += f" LIMIT {int(max_items)}"
        rows = con.execute(query).fetchall()
    finally:
        con.close()

    item_ids = [int(r[0]) for r in rows if r and r[0] is not None]
    if not item_ids:
        print("[!] Không có item_id nào trong scraped_items để refresh.")
        return False

    print(f"[*] Refresh dữ liệu cho {len(item_ids)} sản phẩm hiện có...")
    refreshed = []

    for idx, item_id in enumerate(item_ids, start=1):
        print(f"[-] ({idx}/{len(item_ids)}) Item {item_id}")
        payload = fetch_tiki_product_detail(item_id)
        item = payload.get("data") or payload
        if not isinstance(item, dict) or not item.get("id"):
            continue

        refreshed.append(flatten_tiki_detail_item(item))
        time.sleep(delay_seconds)

    if not refreshed:
        print("[!] Không lấy được dữ liệu mới, giữ nguyên bảng cũ.")
        return False

    df = pd.DataFrame(refreshed).drop_duplicates(subset=["itemid"])
    db_path = save_scraped_items(df, output_dir, replace_table=True)
    print(f"[*] Đã refresh {len(df)} sản phẩm vào: {db_path}")
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tool cào dữ liệu văn bản từ Tiki cho team data.")
    parser.add_argument("--keyword", "-k", type=str, default="áo thun nam", help="Từ khóa sản phẩm cần tìm")
    parser.add_argument("--pages", "-p", type=int, default=3, help="Số trang cần cào (mặc định 3 trang, mỗi trang 50 sản phẩm)")
    parser.add_argument("--output", "-o", type=str, default="../../data", help="Thư mục chứa file DuckDB output")
    
    args = parser.parse_args()
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.normpath(os.path.join(script_dir, args.output))
    
    scrape_tiki(args.keyword, args.pages, output_path)
