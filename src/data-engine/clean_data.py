"""
clean_data.py — Tiki Data Cleaning Pipeline
============================================
Nguồn  : DuckDB (bảng scraped_raw_items_v2, cột du_lieu chứa JSON thô từ Tiki)
Đầu ra : data/staging/products.parquet   — bảng sản phẩm đã clean
         data/mart/products_full.parquet — bảng phân tích cuối cùng (alias)

Cleaning theo yêu cầu leader:
  1. Giá (price)         → bỏ ký tự đ, dấu chấm → Integer
  2. Số lượng bán        → "1,2k" → 1200
  3. Kho hàng (stock)    → "Hết hàng" → 0
  4. Tên sản phẩm        → bỏ emoji, từ khóa rác SEO
  5. Timestamp           → YYYY-MM-DD HH:MM:SS UTC+7
  6. Lấy đúng 7 cột quan trọng + xuất .parquet

Chạy:
  python clean_data.py
  python clean_data.py --db path/to/tiki_scraped_data_raw.duckdb
  python clean_data.py --db path/to/file.duckdb --limit 1000
"""

import re
import os
import json
import logging
import argparse
from datetime import datetime, timezone, timedelta

import duckdb
import pandas as pd
from dotenv import load_dotenv

# ───────────────────────────── CONFIG ──────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# Đường dẫn mặc định
# clean_data.py nằm ở:  src/data-engine/clean_data.py
# DuckDB nằm ở:         data/tiki_scraped_data_raw.duckdb  (gốc project hoặc từ .env)
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_CURRENT_DIR, "..", ".."))
load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))

_env_db = os.getenv("DUCKDB_PATH")
if _env_db:
    DB_PATH = os.path.abspath(_env_db) if os.path.isabs(_env_db) else os.path.abspath(os.path.join(_PROJECT_ROOT, _env_db))
else:
    DB_PATH = os.path.abspath(os.path.join(_PROJECT_ROOT, "data", "tiki_scraped_data_raw.duckdb"))

_DATA_DIR    = os.path.abspath(os.path.join(_PROJECT_ROOT, "data"))
STAGING_DIR  = os.path.join(_DATA_DIR, "staging")
MART_DIR     = os.path.join(_DATA_DIR, "mart")
TABLE_NAME   = "scraped_raw_items_v2"

# Múi giờ UTC+7 (Việt Nam)
VN_TZ = timezone(timedelta(hours=7))

# Từ khóa rác SEO — không dùng \b vì tiếng Việt có dấu làm \b không nhận ranh giới đúng
SEO_NOISE = re.compile(
    r'('
    r'FREESHIP|FREE\s*SHIP|FLASH\s*SALE|CHÍNH\s*HÃNG|HÀNG\s*CHÍNH\s*HÃNG|'
    r'KHUYẾN\s*MÃI|GIẢM\s*GIÁ|GIÁ\s*RẺ|GIÁ\s*SỐC|GIÁ\s*TỐT|'
    r'SIÊU\s*RẺ|SIÊU\s*HOT|ĐỘC\s*QUYỀN|XẢ\s*HÀNG|BÁN\s*CHẠY|'
    r'HÀNG\s*MỚI|TẶNG\s*QUÀ|CHẤT\s*LƯỢNG\s*CAO|'
    r'phong\s+cách\s+\w+|'
    r'rất\s+\w+(\s+\w+){0,3}|'
    r'bao\s+\w+|siêu\s+\w+|cực\s+đẹp|xịn\s+xò|'
    r'out\s+of\s+control|cá\s+tính|'
    r'(?<!\w)HOT(?!\w)'
    r')',
    re.IGNORECASE | re.UNICODE,
)
# Từ đơn lẻ rác còn sót ở cuối chuỗi sau khi đã xóa cụm
TRAILING_JUNK = re.compile(
    r'\s+(đẹp|xịn|chất|hot|cách|tính|hàng)\s*$',
    re.IGNORECASE | re.UNICODE,
)
EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F9FF"
    "\U00002600-\U000027BF"
    "\U0001FA00-\U0001FA9F"
    "]+",
    flags=re.UNICODE,
)


# ─────────────────────────── HELPERS ───────────────────────────────
def clean_price(value) -> int | None:
    """
    Chuyển giá về Integer (VND).
    Tiki trả về số nguyên sạch rồi, nhưng vẫn guard trường hợp chuỗi.
    Ví dụ: "150.000" → 150000 | "đ143,000" → 143000 | 143000 → 143000
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    s = str(value).strip()
    s = re.sub(r'[đĐ₫\s]', '', s)   # bỏ ký tự tiền tệ
    s = re.sub(r'[.,](?=\d{3})', '', s)  # bỏ dấu phân tách hàng nghìn
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return None


def clean_sold(value) -> int | None:
    """
    Chuyển số lượng bán về Integer.
    "1,2k" → 1200 | "10k" → 10000 | 500 → 500
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    s = str(value).strip().lower().replace(',', '.')
    m = re.match(r'([\d.]+)\s*k', s)
    if m:
        return int(float(m.group(1)) * 1000)
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return None


def clean_stock(value) -> int:
    """
    Chuyển tồn kho về Integer.
    "Hết hàng" / 0 / None → 0 | availability=1 → 1 (có hàng)
    """
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    s = str(value).strip().lower()
    if any(x in s for x in ['hết', 'het', 'out', '0']):
        return 0
    if any(x in s for x in ['còn', 'con', 'available', '1']):
        return 1
    return 0


def clean_name(name: str) -> str:
    """
    Làm sạch tên sản phẩm:
    - Bỏ emoji
    - Bỏ từ khóa + cụm rác SEO
    - Bỏ đuôi mã sản phẩm -M189, -AT019, -p117132492
    - Bỏ từ đơn lẻ rác còn sót ở cuối chuỗi
    - Chuẩn hóa khoảng trắng và dấu câu
    - Viết hoa chữ đầu tiên
    """
    if not name:
        return ""
    name = EMOJI_RE.sub('', name)
    name = SEO_NOISE.sub('', name)
    name = TRAILING_JUNK.sub('', name)  # lần 1
    name = TRAILING_JUNK.sub('', name)  # lần 2 phòng sót
    name = re.sub(r'[-_]\s*[A-Za-z]{0,3}\d+\w*$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'(\s*[-|/]\s*){2,}', ' - ', name)
    name = re.sub(r'^[\s\-|/.,_]+|[\s\-|/.,_]+$', '', name)
    name = re.sub(r'^[-–—]+\s*', '', name) 
    name = re.sub(r'\s{2,}', ' ', name).strip()
    if name:
        name = name[0].upper() + name[1:]
    return name


def clean_timestamp(ts_str: str) -> str | None:
    """
    Chuyển timestamp về YYYY-MM-DD HH:MM:SS (UTC+7).
    Hỗ trợ: ISO string, "YYYY-MM-DD HH:MM:SS", None.
    """
    if not ts_str:
        return None
    try:
        # Thử parse ISO format
        dt = datetime.fromisoformat(str(ts_str).replace('Z', '+00:00'))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=VN_TZ)
        else:
            dt = dt.astimezone(VN_TZ)
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        return str(ts_str)[:19]  # fallback: lấy 19 ký tự đầu


def extract_variant_info(badges: list) -> dict:
    """
    Trích thông tin biến thể (Size, Màu) từ badges_new.
    Ví dụ badge text: "4 Size" "2 Màu" → {"so_size": 4, "so_mau": 2}
    """
    result = {"so_size": None, "so_mau": None}
    if not badges or not isinstance(badges, list):
        return result
    for badge in badges:
        arr = badge.get("arr_text") or []
        for item in arr:
            txt = str(item.get("value", "")).strip()
            m_size = re.match(r'(\d+)\s*[Ss]ize', txt)
            m_mau  = re.match(r'(\d+)\s*[Mm]àu', txt)
            if m_size:
                result["so_size"] = int(m_size.group(1))
            if m_mau:
                result["so_mau"] = int(m_mau.group(1))
    return result


# ──────────────────────── ĐỌC TỪ DUCKDB ───────────────────────────
def load_from_duckdb(db_path: str, limit: int = None) -> pd.DataFrame:
    """
    Kết nối DuckDB, đọc bảng scraped_raw_items_v2.
    Trả về DataFrame với các cột gốc.
    """
    log.info(f"[DB] Kết nối: {db_path}")
    con = duckdb.connect(str(db_path), read_only=True)

    limit_clause = f"LIMIT {limit}" if limit else ""
    query = f"""
        SELECT
            thoi_diem,
            nen_tang,
            du_lieu,
            ten_san_pham,
            id_product,
            danh_muc
        FROM {TABLE_NAME}
        WHERE du_lieu IS NOT NULL
        {limit_clause}
    """
    df = con.execute(query).df()
    con.close()

    log.info(f"[DB] Đọc được {len(df):,} bản ghi từ bảng '{TABLE_NAME}'")
    return df


# ──────────────────────── CLEAN TỪNG DÒNG ──────────────────────────
def parse_du_lieu(row: pd.Series) -> dict:
    """
    Parse cột du_lieu (JSON string) → extract và clean các field cần thiết.
    Trả về dict 1 dòng đã clean.
    """
    # Parse JSON
    try:
        item = json.loads(row["du_lieu"]) if isinstance(row["du_lieu"], str) else row["du_lieu"]
    except Exception:
        item = {}

    # ── Giá ──
    price          = clean_price(item.get("price"))
    original_price = clean_price(item.get("original_price"))
    discount_rate  = item.get("discount_rate") or 0

    # ── Số lượng bán ──
    # Tiki search API trả quantity_sold trong impression_info
    quantity_sold = None
    impression = item.get("impression_info")
    if impression and isinstance(impression, list) and len(impression) > 0:
        meta = impression[0].get("metadata") or {}
        quantity_sold = clean_sold(meta.get("quantity_sold"))
    # Fallback: visible_impression_info
    if quantity_sold is None:
        visible = item.get("visible_impression_info") or {}
        amp = visible.get("amplitude") or {}
        quantity_sold = clean_sold(amp.get("all_time_quantity_sold"))

    # ── Tồn kho ──
    stock = clean_stock(item.get("availability"))

    # ── Tên sản phẩm ──
    ten_goc   = item.get("name") or row.get("ten_san_pham") or ""
    ten_clean = clean_name(ten_goc)

    # ── Thương hiệu ──
    brand = item.get("brand_name") or ""
    if brand.lower() in ("no brand", "none", ""):
        brand = "Không có thương hiệu"

    # ── Đánh giá ──
    rating       = item.get("rating_average") or 0
    review_count = item.get("review_count") or 0

    # ── Danh mục ──
    danh_muc = row.get("danh_muc") or item.get("primary_category_name") or ""

    # ── Biến thể (Size, Màu) từ badges ──
    variants = extract_variant_info(item.get("badges_new"))

    # ── Thời gian giao hàng nhanh nhất ──
    fastest_delivery = item.get("fastest_delivery_time")

    # ── Timestamp cào ──
    thoi_diem = clean_timestamp(row.get("thoi_diem"))

    return {
        # 7 cột quan trọng theo yêu cầu leader
        "id_product"      : item.get("id") or row.get("id_product"),
        "ten_san_pham"    : ten_clean,
        "gia"             : price,
        "gia_goc"         : original_price,
        "phan_tram_giam"  : int(discount_rate),
        "so_luong_ban"    : quantity_sold,
        "ton_kho"         : stock,
        # Thêm các cột hữu ích cho dashboard
        "thuong_hieu"     : brand,
        "danh_muc"        : danh_muc,
        "danh_gia_sao"    : round(float(rating), 2) if rating else 0.0,
        "so_luong_review" : int(review_count),
        "so_size"         : variants["so_size"],
        "so_mau"          : variants["so_mau"],
        "giao_hang_som"   : fastest_delivery,
        "nen_tang"        : row.get("nen_tang", "tiki"),
        "thoi_diem_cao"   : thoi_diem,
        # Metadata
        "id_seller"       : item.get("seller_id"),
        "ten_seller"      : item.get("seller_name"),
        "is_chinh_hang"   : bool(item.get("is_authentic")),
        "is_tiki_verified": bool(item.get("tiki_verified")),
        "url"             : f"https://tiki.vn/{item.get('url_path', '')}",
    }


def clean_batch(df_raw: pd.DataFrame) -> pd.DataFrame:
    """
    Áp dụng parse_du_lieu cho toàn bộ DataFrame.
    Trả về DataFrame đã clean, dedup theo id_product.
    """
    log.info(f"[CLEAN] Đang xử lý {len(df_raw):,} bản ghi...")
    records = []
    errors  = 0

    for _, row in df_raw.iterrows():
        try:
            records.append(parse_du_lieu(row))
        except Exception as e:
            errors += 1
            log.debug(f"  ✘ id={row.get('id_product')}: {e}")

    if errors:
        log.warning(f"[CLEAN] {errors} bản ghi lỗi (đã bỏ qua)")

    df = pd.DataFrame(records)

    # Ép kiểu
    df["id_product"]       = pd.to_numeric(df["id_product"],       errors="coerce").astype("Int64")
    df["gia"]              = pd.to_numeric(df["gia"],               errors="coerce").astype("Int64")
    df["gia_goc"]          = pd.to_numeric(df["gia_goc"],           errors="coerce").astype("Int64")
    df["phan_tram_giam"]   = pd.to_numeric(df["phan_tram_giam"],    errors="coerce").astype("Int64")
    df["so_luong_ban"]     = pd.to_numeric(df["so_luong_ban"],      errors="coerce").astype("Int64")
    df["ton_kho"]          = pd.to_numeric(df["ton_kho"],           errors="coerce").astype("Int64")
    df["so_luong_review"]  = pd.to_numeric(df["so_luong_review"],   errors="coerce").astype("Int64")
    df["id_seller"]        = pd.to_numeric(df["id_seller"],         errors="coerce").astype("Int64")
    df["so_size"]          = pd.array(df["so_size"].tolist(),  dtype="Int64")
    df["so_mau"]           = pd.array(df["so_mau"].tolist(),   dtype="Int64")

    # Dedup — giữ bản ghi mới nhất nếu cùng id_product
    before = len(df)
    df = df.drop_duplicates(subset=["id_product"], keep="last")
    if before != len(df):
        log.info(f"[CLEAN] Dedup: {before} → {len(df)} dòng (bỏ {before - len(df)} trùng)")

    log.info(f"[CLEAN] Hoàn thành: {len(df):,} sản phẩm sạch, {len(df.columns)} cột")
    return df


# ──────────────────────── XUẤT PARQUET ────────────────────────────
def save_parquet(df: pd.DataFrame, folder: str, name: str):
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{name}.parquet")
    df.to_parquet(path, index=False, engine="pyarrow")
    size_mb = os.path.getsize(path) / 1024 / 1024
    log.info(f"[SAVE] {path}  ({len(df):,} dòng | {size_mb:.2f} MB)")
    return path


# ─────────────────────────── MAIN ──────────────────────────────────
def main(db_path: str, limit: int = None):
    log.info("=" * 55)
    log.info("TIKI DATA CLEANING PIPELINE")
    log.info("=" * 55)

    # 1. Đọc từ DuckDB
    df_raw = load_from_duckdb(db_path, limit=limit)
    if df_raw.empty:
        log.error("Không có dữ liệu trong bảng. Dừng.")
        return

    # 2. Clean
    df_clean = clean_batch(df_raw)

    # 3. Xuất parquet
    log.info("=" * 55)
    log.info("XUẤT FILE PARQUET")
    log.info("=" * 55)

    base     = os.path.dirname(os.path.abspath(db_path))
    staging  = os.path.join(base, "staging")
    mart     = os.path.join(base, "mart")

    staging_path = save_parquet(df_clean, staging, "products")
    mart_path    = save_parquet(df_clean, mart,    "products_full")

    # 4. Summary
    print("\n📊 Kết quả clean:")
    print(f"   Tổng sản phẩm : {len(df_clean):,}")
    print(f"   Danh mục      : {df_clean['danh_muc'].nunique()} loại")
    print(f"   Thương hiệu   : {df_clean['thuong_hieu'].nunique()} brand")
    print(f"   Giá thấp nhất : {df_clean['gia'].min():,} VND")
    print(f"   Giá cao nhất  : {df_clean['gia'].max():,} VND")
    print(f"\n📁 Output:")
    print(f"   {staging_path}")
    print(f"   {mart_path}")
    print(f"\n✅ Pipeline hoàn thành!")


# ───────────────────────────── CLI ─────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Tiki Data Cleaning Pipeline — đọc DuckDB, xuất Parquet",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
Ví dụ:
  python clean_data.py
  python clean_data.py --db data/tiki_scraped_data_raw.duckdb
  python clean_data.py --db data/tiki_scraped_data_raw.duckdb --limit 500
        """
    )
    parser.add_argument(
        "--db", "-d",
        default=DB_PATH,
        help=f"Đường dẫn file DuckDB (default: ../../data/tiki_scraped_data_raw.duckdb)"
    )
    parser.add_argument(
        "--limit", "-l",
        type=int, default=None,
        help="Giới hạn số bản ghi đọc (dùng để test, mặc định đọc hết)"
    )
    args = parser.parse_args()
    main(db_path=args.db, limit=args.limit)