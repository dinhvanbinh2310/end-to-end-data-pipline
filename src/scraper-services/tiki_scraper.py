import os
import time
import json
import argparse
from datetime import datetime
from pathlib import Path
from typing import Any, cast

import duckdb
import pandas as pd
import requests

RAW_DB_FILENAME = "tiki_scraped_data_raw.duckdb"
RAW_TABLE_NAME = "scraped_raw_items_v2"


def build_db_path(output_dir: str) -> str:
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    return os.path.join(output_dir, RAW_DB_FILENAME)


def table_exists(con: duckdb.DuckDBPyConnection, table_name: str) -> bool:
    row = con.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?",
        [table_name],
    ).fetchone()
    return bool(row and row[0])


def ensure_raw_table_schema(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {RAW_TABLE_NAME} (
            thoi_diem VARCHAR,
            nen_tang VARCHAR,
            du_lieu JSON,
            ten_san_pham VARCHAR,
            id_product BIGINT,
            danh_muc VARCHAR,
            tu_khoa VARCHAR,
            gia_hien_tai BIGINT,
            gia_goc BIGINT,
            diem_danh_gia DOUBLE,
            luot_mua BIGINT,
            product_url VARCHAR,
            kieu_cao VARCHAR
        )
        """
    )

    existing_cols = {
        row[0].lower()
        for row in con.execute(f"DESCRIBE {RAW_TABLE_NAME}").fetchall()
    }
    required_cols: dict[str, str] = {
        "danh_muc": "VARCHAR",
        "tu_khoa": "VARCHAR",
        "gia_hien_tai": "BIGINT",
        "gia_goc": "BIGINT",
        "diem_danh_gia": "DOUBLE",
        "luot_mua": "BIGINT",
        "product_url": "VARCHAR",
        "kieu_cao": "VARCHAR",
    }
    for col, dtype in required_cols.items():
        if col not in existing_cols:
            con.execute(f"ALTER TABLE {RAW_TABLE_NAME} ADD COLUMN {col} {dtype}")


def fetch_tiki_search_items(keyword: str, page_number: int, limit: int = 50) -> dict:
    url = "https://tiki.vn/api/v2/products"
    params = {
        "limit": limit,
        "q": keyword,
        "page": page_number + 1,
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
    }

    try:
        r = requests.get(url, params=params, headers=headers, timeout=15)
        if r.status_code != 200:
            print(f"[!] Lỗi HTTP khi gọi API Tiki: {r.status_code}")
            return {}
        return r.json()
    except Exception as e:
        print(f"[!] Lỗi kết nối Tiki: {e}")
        return {}


def fetch_tiki_product_detail(product_id: int) -> dict:
    url = f"https://tiki.vn/api/v2/products/{product_id}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
    }

    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code != 200:
            print(f"[!] Lỗi HTTP khi gọi chi tiết sản phẩm {product_id}: {r.status_code}")
            return {}
        return r.json()
    except Exception as e:
        print(f"[!] Lỗi kết nối khi lấy chi tiết sản phẩm {product_id}: {e}")
        return {}


def extract_product_url(item: dict[str, Any]) -> str:
    short_url = item.get("short_url")
    if short_url:
        return str(short_url)
    url_path = item.get("url_path")
    if url_path:
        return f"https://tiki.vn/{url_path}"
    return ""


def extract_sold(item: dict[str, Any]) -> int | None:
    sold_info = item.get("quantity_sold")
    if isinstance(sold_info, dict):
        return sold_info.get("value")
    if isinstance(sold_info, (int, float)):
        return int(sold_info)
    return None


def _volatility_score(item: dict[str, Any]) -> tuple[int, float, int]:
    """Higher score means product is a better candidate for change tracking."""
    sold = extract_sold(item)
    rating = item.get("rating_average")
    price = item.get("price") or item.get("list_price") or item.get("original_price") or 0

    sold_value = int(sold) if isinstance(sold, (int, float)) else 0
    rating_value = float(rating) if isinstance(rating, (int, float)) else 0.0
    price_value = int(price) if isinstance(price, (int, float)) else 0
    return (sold_value, rating_value, price_value)


def flatten_tiki_item(
    item: dict[str, Any],
    danh_muc: str = "",
    tu_khoa: str = "",
    kieu_cao: str = "new",
    snapshot_time: datetime | str | None = None,
) -> dict[str, Any]:
    if isinstance(snapshot_time, datetime):
        thoi_diem = snapshot_time.strftime("%Y-%m-%d %H:%M:%S")
    elif isinstance(snapshot_time, str) and snapshot_time.strip():
        thoi_diem = snapshot_time.strip()
    else:
        thoi_diem = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return {
        "thoi_diem": thoi_diem,
        "nen_tang": "tiki",
        "du_lieu": json.dumps(item, ensure_ascii=False),
        "ten_san_pham": item.get("name", ""),
        "id_product": item.get("id"),
        "danh_muc": danh_muc,
        "tu_khoa": tu_khoa,
        "gia_hien_tai": item.get("price") or item.get("list_price") or item.get("original_price"),
        "gia_goc": item.get("original_price") or item.get("list_price") or item.get("price"),
        "diem_danh_gia": item.get("rating_average"),
        "luot_mua": extract_sold(item),
        "product_url": extract_product_url(item),
        "kieu_cao": kieu_cao,
    }


def append_rows_to_raw_db(rows: list[dict[str, Any]], output_dir: str, dedupe_hours: int = 0) -> tuple[int, str]:
    db_path = build_db_path(output_dir)
    if not rows:
        return 0, db_path

    df = pd.DataFrame(rows)
    if "id_product" not in df.columns:
        return 0, db_path

    df = df.dropna(subset=["id_product"])
    df = df.drop_duplicates(subset=["id_product"], keep="last")
    if df.empty:
        return 0, db_path

    con: duckdb.DuckDBPyConnection | None = None
    try:
        con = duckdb.connect(db_path)
        ensure_raw_table_schema(con)
        cols = [row[0] for row in con.execute(f"DESCRIBE {RAW_TABLE_NAME}").fetchall()]
        for col in cols:
            if col not in df.columns:
                df[col] = None
        df = df[cols]

        if dedupe_hours > 0:
            recent_ids = {
                row[0]
                for row in con.execute(
                    f"""
                    SELECT id_product
                    FROM {RAW_TABLE_NAME}
                    WHERE id_product IS NOT NULL
                      AND TRY_CAST(thoi_diem AS TIMESTAMP) >= NOW() - INTERVAL '{int(dedupe_hours)} hour'
                    """
                ).fetchall()
            }
            id_col = cast(pd.Series, df["id_product"])
            mask = id_col.isin(list(recent_ids))
            df = cast(pd.DataFrame, df.loc[~mask])

        if df.empty:
            return 0, db_path

        con.append(RAW_TABLE_NAME, cast(pd.DataFrame, df))
        return len(df), db_path
    except Exception as e:
        print(f"[!] LỖI DuckDB: {e}")
        return 0, db_path
    finally:
        if con is not None:
            con.close()


def scrape_tiki(
    keyword: str,
    max_pages: int,
    output_dir: str,
    danh_muc: str = "",
    page_limit: int = 50,
    dedupe_hours: int = 0,
    snapshot_time: datetime | str | None = None,
):
    print(f"[*] Bắt đầu cào dữ liệu từ Tiki cho từ khóa: '{keyword}'")
    all_items: list[dict[str, Any]] = []
    run_snapshot_time = snapshot_time or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for page in range(max_pages):
        print(f"[-] Đang cào trang {page + 1}...")
        data = fetch_tiki_search_items(keyword, page, page_limit)
        items = data.get("data") or []

        if not items:
            print("[-] Không còn dữ liệu hoặc bị giới hạn kết quả.")
            break

        for item in items:
            if isinstance(item, dict):
                all_items.append(
                    flatten_tiki_item(
                        item,
                        danh_muc=danh_muc,
                        tu_khoa=keyword,
                        kieu_cao="new",
                        snapshot_time=run_snapshot_time,
                    )
                )

        if len(items) < page_limit:
            break

        time.sleep(1.2)

    inserted_count, db_path = append_rows_to_raw_db(all_items, output_dir, dedupe_hours=dedupe_hours)
    if inserted_count == 0:
        print("[*] Không có sản phẩm mới để thêm vào DB.")
        return

    print(f"[*] THÀNH CÔNG: Đã thêm {inserted_count} record mới vào {db_path}")


def refresh_existing_tiki_items(
    output_dir: str,
    max_items: int | None = None,
    delay_seconds: float = 0.3,
    snapshot_time: datetime | str | None = None,
) -> bool:
    db_path = build_db_path(output_dir)
    if not os.path.exists(db_path):
        print(f"[!] Chưa tìm thấy DB tại: {db_path}")
        return False

    con: duckdb.DuckDBPyConnection | None = None
    try:
        con = duckdb.connect(db_path)
        ensure_raw_table_schema(con)
        query = f"SELECT DISTINCT id_product FROM {RAW_TABLE_NAME} WHERE id_product IS NOT NULL ORDER BY id_product DESC"
        if max_items and max_items > 0:
            query += f" LIMIT {int(max_items)}"
        rows = con.execute(query).fetchall()
    finally:
        if con is not None:
            con.close()

    item_ids = [int(r[0]) for r in rows if r and r[0] is not None]
    if not item_ids:
        print(f"[!] Không có id_product nào trong {RAW_TABLE_NAME} để sync.")
        return False

    print(f"[*] Sync giá cho {len(item_ids)} sản phẩm cũ...")
    refreshed: list[dict[str, Any]] = []
    run_snapshot_time = snapshot_time or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for idx, item_id in enumerate(item_ids, start=1):
        print(f"[-] ({idx}/{len(item_ids)}) Product {item_id}")
        payload = fetch_tiki_product_detail(item_id)
        item = payload.get("data") or payload
        if isinstance(item, dict) and item.get("id"):
            refreshed.append(
                flatten_tiki_item(item, danh_muc="sync_existing", kieu_cao="sync", snapshot_time=run_snapshot_time)
            )
        time.sleep(delay_seconds)

    inserted_count, db_path = append_rows_to_raw_db(refreshed, output_dir, dedupe_hours=0)
    print(f"[*] Sync xong. Đã thêm {inserted_count} record mới vào {db_path}")
    return inserted_count > 0


def crawl_new_products(
    keyword: str,
    quantity: int,
    output_dir: str,
    danh_muc: str = "giao_dien",
    snapshot_time: datetime | str | None = None,
) -> dict[str, Any]:
    quantity = int(quantity)

    # Pull a wider candidate pool, then keep the most "volatile" products.
    candidate_limit = min(max(quantity * 10, 50), 100)
    data = fetch_tiki_search_items(keyword, page_number=0, limit=candidate_limit)
    items = [item for item in (data.get("data") or []) if isinstance(item, dict)]
    items = sorted(items, key=_volatility_score, reverse=True)[:quantity]

    run_snapshot_time = snapshot_time or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    rows = [
        flatten_tiki_item(item, danh_muc=danh_muc, tu_khoa=keyword, kieu_cao="new", snapshot_time=run_snapshot_time)
        for item in items
    ]
    inserted_count, db_path = append_rows_to_raw_db(rows, output_dir, dedupe_hours=0)
    return {
        "inserted": inserted_count,
        "requested": quantity,
        "fetched": len(rows),
        "candidate_pool": len(data.get("data") or []),
        "selection_strategy": "top_sold_rating_price",
        "db_path": db_path,
    }


def sync_prices_from_existing(
    output_dir: str,
    max_items: int,
    delay_seconds: float = 0.3,
    snapshot_time: datetime | str | None = None,
) -> dict[str, Any]:
    ok = refresh_existing_tiki_items(
        output_dir=output_dir,
        max_items=max_items,
        delay_seconds=delay_seconds,
        snapshot_time=snapshot_time,
    )
    return {
        "success": ok,
        "max_items": max_items,
        "db_path": build_db_path(output_dir),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tool cào dữ liệu từ Tiki.")
    parser.add_argument("--keyword", "-k", type=str, default="áo thun nam", help="Từ khóa sản phẩm cần tìm")
    parser.add_argument("--pages", "-p", type=int, default=1, help="Số trang cần cào")
    parser.add_argument("--output", "-o", type=str, default="../../data", help="Thư mục chứa file DuckDB output")
    parser.add_argument("--danh-muc", type=str, default="cli", help="Danh mục gán cho record")

    args = parser.parse_args()
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.normpath(os.path.join(script_dir, args.output))
    scrape_tiki(args.keyword, args.pages, output_path, danh_muc=args.danh_muc)
