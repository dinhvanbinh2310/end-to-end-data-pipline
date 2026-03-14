import os
import time
import requests
import pandas as pd
import duckdb
from datetime import datetime
from pathlib import Path
import argparse

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

import json

def flatten_tiki_item(item: dict, danh_muc: str = "") -> dict:
    # Lấy dữ liệu theo đúng chuẩn Migration V2 của sếp
    return {
        "thoi_diem": str(datetime.now()),
        "nen_tang": "tiki",
        "du_lieu": json.dumps(item, ensure_ascii=False), # Toàn bộ JSON trả về từ API
        "ten_san_pham": item.get("name", ""),
        "id_product": item.get("id"),
        "danh_muc": danh_muc
    }

def scrape_tiki(keyword: str, max_pages: int, output_dir: str, danh_muc: str = ""):
    print(f"[*] Bắt đầu cào DATA THÔ TOÀN BỘ từ Tiki cho từ khóa: '{keyword}'")
    
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
                row = flatten_tiki_item(it, danh_muc)
                all_items.append(row)
            except Exception as e:
                print(f"[!] Lỗi phân tích item: {e}")
                pass
        
        if len(items) < limit:
            break
            
        time.sleep(1.5)  # Delay để không bị block IP

    if not all_items:
        print("[!] Không có dữ liệu nào được cào về từ Tiki.")
        return

    # Lưu dữ liệu ra Dataframe
    df = pd.DataFrame(all_items)
    
    # Loại bỏ dữ liệu trùng lặp theo id_product
    df = df.drop_duplicates(subset=['id_product'])
    
    # Sắp xếp đúng thứ tự cột migration
    cols = ["thoi_diem", "nen_tang", "du_lieu", "ten_san_pham", "id_product", "danh_muc"]
    df = df[cols]
    
    # Đảm bảo Project Folder Data tồn tại
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    db_path = os.path.join(output_dir, "tiki_scraped_data_raw.duckdb")
    
    # Kết nối DuckDB và Insert thẳng vào Table (không create / drop nữa)
    try:
        con = duckdb.connect(db_path)
        
        # Lọc bỏ id_product đã cào trong vòng 1 tiếng qua (tránh trùng trong cùng 1 chu kỳ)
        # Nếu record > 1 tiếng rồi thì cho cào lại bình thường (fresh data)
        recent_ids = set(
            row[0] for row in con.execute("""
                SELECT id_product 
                FROM scraped_raw_items_v2 
                WHERE id_product IS NOT NULL
                  AND TRY_CAST(thoi_diem AS TIMESTAMP) >= NOW() - INTERVAL '1 hour'
            """).fetchall()
        )
        df = df[~df["id_product"].isin(recent_ids)]
        
        if df.empty:
            print(f"[*] Không có sản phẩm mới (toàn bộ đã cào trong 1h qua). Bỏ qua.")
            con.close()
            return
        
        # Sẽ báo lỗi nếu bảng chưa tồn tại (chưa chạy migration)
        con.append("scraped_raw_items_v2", df)
        con.close()
        
        print(f"[*] THÀNH CÔNG: Đã thêm {len(df)} sản phẩm MỚI vào DuckDB: {db_path} (Bảng: scraped_raw_items_v2)")
    except duckdb.CatalogException:
        print("[!] LỖI CƠ SỞ DỮ LIỆU: Bảng 'scraped_raw_items_v2' chưa được tạo!")
        print("[!] Hướng dẫn: Vui lòng chạy Migration trước bằng lệnh: python src/migration/create_raw_table.py")
    except Exception as e:
        print(f"[!] LỖI DuckDB: {e}")
    print("[*] Hoàn tất! Team Data có thể sử dụng file này để test clean text.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tool cào dữ liệu văn bản từ Tiki cho team data.")
    parser.add_argument("--keyword", "-k", type=str, default="áo thun nam", help="Từ khóa sản phẩm cần tìm")
    parser.add_argument("--pages", "-p", type=int, default=3, help="Số trang cần cào (mặc định 3 trang, mỗi trang 50 sản phẩm)")
    parser.add_argument("--output", "-o", type=str, default="../../data", help="Thư mục chứa file DuckDB output")
    
    args = parser.parse_args()
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.normpath(os.path.join(script_dir, args.output))
    
    scrape_tiki(args.keyword, args.pages, output_path)
