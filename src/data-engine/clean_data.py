"""
Bước 1 — CLEAN JSON:
  Input  : data/raw/*.json                 
  Output : data/staging/clean/<item_id>.json   

  Cleaning gồm:
    - Xóa 5 section không cần thiết ở tầng data{}

Bước 2 — SPLIT & MERGE thành CSV:
  Output : data/staging/products.csv          
           data/staging/models.csv
           data/staging/attributes.csv
           data/staging/shops.csv
           data/staging/vouchers.csv
           data/mart/products_full.csv

Cách chạy:
  python clean_data.py                         # batch: toàn bộ data/raw/*.json
  python clean_data.py --input path/file.json  # 1 file cụ thể
  python clean_data.py --json-only             # chỉ clean JSON, không split CSV
"""

import json
import os
import glob
import argparse
import logging
from datetime import datetime, timezone

import pandas as pd

# ───────────────────────────── CONFIG ──────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

RAW_DIR           = "data/raw"
STAGING_DIR       = "data/staging"
STAGING_CLEAN_DIR = "data/staging/clean"   # JSON đã clean, 1 file/sản phẩm
MART_DIR          = "data/mart"

# 5 section ở tầng data{} 
SECTIONS_TO_REMOVE = {
    "flash_sale_booked",
    "featured_voucher",
    "live_stream",
    "shop_vouchers_meta",
    "promotion_drawer",
}


# ─────────────────────────── HELPERS ───────────────────────────────
def to_datetime(unix_ts) -> str:
    if not unix_ts:
        return None
    return datetime.fromtimestamp(unix_ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def ensure_dirs(*dirs):
    for d in dirs:
        os.makedirs(d, exist_ok=True)


def find_json_files(raw_dir: str) -> list:
    return sorted(glob.glob(os.path.join(raw_dir, "*.json")))


# ──────────────────────── BƯỚC 1: CLEAN JSON ───────────────────────
def clean_json(input_path: str) -> dict:
    """Đọc 1 file JSON thô, xóa 5 section không cần thiết."""
    with open(input_path, encoding="utf-8") as f:
        raw = json.load(f)

    if raw.get("data", {}).get("item") is None:
        raise ValueError(f"Không tìm thấy 'data.item' trong {input_path}")

    for key in SECTIONS_TO_REMOVE:
        raw["data"].pop(key, None)

    return raw


def save_clean_json(cleaned: dict, output_dir: str) -> str:
    """Lưu JSON đã clean, đặt tên theo item_id."""
    item_id = cleaned.get("data", {}).get("item", {}).get("item_id", "unknown")
    path = os.path.join(output_dir, f"item_{item_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, ensure_ascii=False, indent=2)
    return path


# ──────────────────────── BƯỚC 2: BUILD CSV ────────────────────────
def extract_sections(cleaned: dict) -> dict:
    data = cleaned.get("data", {})
    return {
        "item"               : data.get("item", {}),
        "shop_detailed"      : data.get("shop_detailed") or {},
        "product_review"     : data.get("product_review") or {},
        "product_attributes" : data.get("product_attributes") or {},
        "shop_vouchers"      : data.get("shop_vouchers") or [],
    }


def build_products(sections: dict) -> pd.DataFrame:
    item   = sections["item"]
    review = sections["product_review"]

    record = {
        "item_id"                   : item.get("item_id"),
        "shop_id"                   : item.get("shop_id"),
        "cat_id"                    : item.get("cat_id"),
        "category_name"             : (
            item["categories"][0].get("display_name")
            if item.get("categories") else None
        ),
        "title"                     : (item.get("title") or "").strip(),
        "description"               : (item.get("description") or "").strip() or None,
        "brand"                     : item.get("brand"),
        "condition"                 : "Mới" if item.get("condition") == 1 else "Đã dùng",
        "item_status"               : item.get("item_status"),
        "shop_location"             : item.get("shop_location"),
        "currency"                  : item.get("currency", "VND"),
        "price_min"                 : item.get("price_min"),
        "price_max"                 : item.get("price_max"),
        "price_min_before_discount" : item.get("price_min_before_discount"),
        "price_max_before_discount" : item.get("price_max_before_discount"),
        "discount_pct"              : item.get("show_discount"),
        "rating_star"               : (
            item["item_rating"].get("rating_star")
            if item.get("item_rating") else None
        ),
        "total_rating_count"        : review.get("total_rating_count"),
        "sold_display"              : review.get("sold_count_display"),
        "liked_count"               : review.get("liked_count"),
        "cmt_count"                 : review.get("cmt_count"),
        "is_service_by_shopee"      : item.get("is_service_by_shopee"),
        "is_pre_order"              : item.get("is_pre_order"),
        "is_free_shipping"          : item.get("is_free_shipping"),
        "stock_display"             : item.get("stock_display"),
        "created_at"                : to_datetime(item.get("ctime")),
    }

    df = pd.DataFrame([record])
    for col in ["item_id", "shop_id", "cat_id", "discount_pct",
                "total_rating_count", "liked_count", "cmt_count"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    df["rating_star"] = pd.to_numeric(df["rating_star"], errors="coerce").round(2)
    return df


def build_models(sections: dict) -> pd.DataFrame:
    item       = sections["item"]
    models_raw = item.get("models") or []
    if not models_raw:
        return pd.DataFrame()

    records = []
    for m in models_raw:
        extinfo = m.get("extinfo") or {}
        records.append({
            "model_id"              : m.get("model_id"),
            "item_id"               : m.get("item_id"),
            "name"                  : (m.get("name") or "").strip(),
            "status"                : m.get("status"),
            "price"                 : m.get("price"),
            "price_before_discount" : m.get("price_before_discount"),
            "normal_stock"          : m.get("normal_stock"),
            "sold"                  : m.get("sold"),
            "has_stock"             : m.get("has_stock"),
            "is_clickable"          : m.get("is_clickable"),
            "is_grayout"            : m.get("is_grayout"),
            "is_pre_order"          : extinfo.get("is_pre_order"),
            "estimated_days"        : extinfo.get("estimated_days"),
        })

    df = pd.DataFrame(records)
    df["model_id"] = pd.to_numeric(df["model_id"], errors="coerce").astype("Int64")
    df["item_id"]  = pd.to_numeric(df["item_id"],  errors="coerce").astype("Int64")
    df["sold"]     = pd.to_numeric(df["sold"],      errors="coerce").astype("Int64")
    return df.drop_duplicates(subset=["model_id"])


def build_attributes(sections: dict) -> pd.DataFrame:
    item         = sections["item"]
    product_attr = sections["product_attributes"]
    attrs_raw    = product_attr.get("attrs") or item.get("attributes") or []
    if not attrs_raw:
        return pd.DataFrame()

    records = [
        {
            "item_id"    : item.get("item_id"),
            "attr_id"    : a.get("id"),
            "attr_name"  : (a.get("name") or "").strip(),
            "attr_value" : str(a.get("value") or "").strip(),
            "val_id"     : a.get("val_id"),
        }
        for a in attrs_raw
    ]
    df = pd.DataFrame(records)
    df["item_id"] = pd.to_numeric(df["item_id"], errors="coerce").astype("Int64")
    df["attr_id"] = pd.to_numeric(df["attr_id"], errors="coerce").astype("Int64")
    return df


def build_shops(sections: dict) -> pd.DataFrame:
    item = sections["item"]
    shop = sections["shop_detailed"]

    record = {
        "shop_id"             : shop.get("shopid") or item.get("shop_id"),
        "shop_name"           : shop.get("name"),
        "shop_location"       : item.get("shop_location"),
        "is_official_shop"    : shop.get("is_official_shop"),
        "is_preferred_plus"   : shop.get("is_preferred_plus_seller"),
        "is_shopee_verified"  : shop.get("is_shopee_verified"),
        "rating_star"         : round(shop["rating_star"], 2) if shop.get("rating_star") else None,
        "rating_good"         : shop.get("rating_good"),
        "rating_normal"       : shop.get("rating_normal"),
        "rating_bad"          : shop.get("rating_bad"),
        "follower_count"      : shop.get("follower_count"),
        "item_count"          : shop.get("item_count"),
        "response_rate"       : shop.get("response_rate"),
        "response_time"       : shop.get("response_time"),
        "is_service_by_shopee": item.get("is_service_by_shopee"),
        "shop_created_at"     : to_datetime(shop.get("ctime")),
    }

    df = pd.DataFrame([record])
    df["shop_id"] = pd.to_numeric(df["shop_id"], errors="coerce").astype("Int64")
    for col in ["rating_good", "rating_normal", "rating_bad",
                "follower_count", "item_count", "response_rate", "response_time"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    return df


def build_vouchers(sections: dict) -> pd.DataFrame:
    vouchers_raw = sections["shop_vouchers"]
    if not vouchers_raw:
        return pd.DataFrame()

    records = [
        {
            "promotion_id"         : v.get("promotionid"),
            "shop_id"              : v.get("shop_id"),
            "shop_name"            : v.get("shop_name"),
            "voucher_code"         : v.get("voucher_code"),
            "min_spend"            : v.get("min_spend"),
            "discount_pct"         : v.get("discount_percentage"),
            "discount_value"       : v.get("discount_value"),
            "reward_cap"           : v.get("reward_cap"),
            "usage_limit_per_user" : v.get("usage_limit_per_user"),
            "remaining_usage"      : v.get("remaining_usage_limit"),
            "percentage_used"      : v.get("percentage_used"),
            "start_time"           : to_datetime(v.get("start_time")),
            "end_time"             : to_datetime(v.get("end_time")),
            "is_official_shop"     : v.get("is_shop_official"),
        }
        for v in vouchers_raw
    ]
    df = pd.DataFrame(records)
    df["promotion_id"] = pd.to_numeric(df["promotion_id"], errors="coerce").astype("Int64")
    df["shop_id"]      = pd.to_numeric(df["shop_id"],      errors="coerce").astype("Int64")
    for col in ["discount_pct", "usage_limit_per_user", "remaining_usage", "percentage_used"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    return df.drop_duplicates(subset=["promotion_id"])


def build_mart(products, models, attributes, shops) -> pd.DataFrame:
    df = products.copy()

    if not models.empty:
        cheapest = (
            models[models["has_stock"] == True]
            .sort_values("price")
            .drop_duplicates(subset=["item_id"])
            [["item_id", "price", "name", "normal_stock", "sold", "estimated_days"]]
            .rename(columns={
                "price"         : "cheapest_price",
                "name"          : "cheapest_variant",
                "normal_stock"  : "cheapest_stock",
                "sold"          : "cheapest_sold",
                "estimated_days": "delivery_days",
            })
        )
        df = df.merge(cheapest, on="item_id", how="left")

    if not shops.empty:
        shop_cols = [c for c in ["shop_id", "shop_name", "is_official_shop",
                                  "rating_star", "follower_count", "response_rate"]
                     if c in shops.columns]
        df = df.merge(
            shops[shop_cols].rename(columns={"rating_star": "shop_rating"}),
            on="shop_id", how="left",
        )

    if not attributes.empty:
        pivot = (
            attributes
            .pivot_table(index="item_id", columns="attr_name",
                         values="attr_value", aggfunc="first")
            .reset_index()
        )
        pivot.columns = [
            str(c).lower().replace(" ", "_").replace("/", "_")
            for c in pivot.columns
        ]
        df = df.merge(pivot, on="item_id", how="left")

    return df


# ───────────────────── SAVE CSV  ─────────────────────
def save_csv(df: pd.DataFrame, folder: str, name: str, dedup_col: str = None):
    """
    Ghi CSV theo kiểu upsert:
      - File chưa tồn tại  → ghi mới
      - File đã tồn tại    → load lên, gộp, dedup theo dedup_col, ghi lại
    Nhờ đó chạy nhiều lần / nhiều batch vẫn không bị trùng dữ liệu.
    """
    if df.empty:
        return

    path = os.path.join(folder, f"{name}.csv")

    if os.path.exists(path) and dedup_col:
        existing = pd.read_csv(path, dtype=str)
        combined = pd.concat([existing, df.astype(str)], ignore_index=True)
        combined = combined.drop_duplicates(subset=[dedup_col], keep="last")
        combined.to_csv(path, index=False, encoding="utf-8-sig")
        log.info(f"[SAVE] {path}  ({len(combined)} dòng tổng, +{len(df)} từ batch này)")
    else:
        df.to_csv(path, index=False, encoding="utf-8-sig")
        log.info(f"[SAVE] {path}  ({len(df)} dòng, {len(df.columns)} cột)")


# ─────────────────────────── PIPELINE ──────────────────────────────
def process_one(input_path: str, json_only: bool = False) -> dict:
    """Xử lý 1 file JSON → trả về dict các DataFrame."""
    cleaned = clean_json(input_path)
    item    = cleaned["data"]["item"]
    log.info(f"  ✔ item_id={item.get('item_id')}  \"{str(item.get('title',''))[:45]}\"")

    clean_path = save_clean_json(cleaned, STAGING_CLEAN_DIR)
    log.info(f"  → JSON clean: {clean_path}")

    if json_only:
        return {}

    sections = extract_sections(cleaned)
    return {
        "products"  : build_products(sections),
        "models"    : build_models(sections),
        "attributes": build_attributes(sections),
        "shops"     : build_shops(sections),
        "vouchers"  : build_vouchers(sections),
    }


def main(input_path: str = None, json_only: bool = False):
    ensure_dirs(STAGING_DIR, STAGING_CLEAN_DIR, MART_DIR)

    # Xác định danh sách file cần xử lý
    files = [input_path] if input_path else find_json_files(RAW_DIR)

    if not files:
        log.error(f"Không tìm thấy file JSON nào trong {RAW_DIR}/")
        return

    log.info("=" * 55)
    log.info(f"TÌM THẤY {len(files)} FILE JSON → BẮT ĐẦU XỬ LÝ")
    log.info("=" * 55)

    # ── BATCH LOOP: xử lý từng file, thu thập DataFrame ──
    all_products, all_models, all_attributes = [], [], []
    all_shops, all_vouchers = [], []
    ok, fail = 0, 0

    for i, fpath in enumerate(files, 1):
        log.info(f"[{i}/{len(files)}] {os.path.basename(fpath)}")
        try:
            dfs = process_one(fpath, json_only=json_only)
            if dfs:
                all_products.append(dfs["products"])
                all_models.append(dfs["models"])
                all_attributes.append(dfs["attributes"])
                all_shops.append(dfs["shops"])
                all_vouchers.append(dfs["vouchers"])
            ok += 1
        except Exception as e:
            log.error(f"  ✘ Lỗi khi xử lý {os.path.basename(fpath)}: {e}")
            fail += 1

    log.info(f"\n✅ Xử lý xong: {ok} file thành công" +
             (f", {fail} file lỗi" if fail else ""))

    if json_only or not all_products:
        return

    # ── MERGE tất cả batch lại, dedup ──
    log.info("=" * 55)
    log.info("MERGE & LƯU CSV")
    log.info("=" * 55)

    def safe_concat(lst):
        lst = [df for df in lst if df is not None and not df.empty]
        return pd.concat(lst, ignore_index=True) if lst else pd.DataFrame()

    df_products   = safe_concat(all_products).drop_duplicates(subset=["item_id"],     keep="last")
    df_models_all = safe_concat(all_models)
    df_models     = df_models_all.drop_duplicates(subset=["model_id"], keep="last") \
                    if not df_models_all.empty else pd.DataFrame()
    df_attributes = safe_concat(all_attributes)
    df_shops_all  = safe_concat(all_shops)
    df_shops      = df_shops_all.drop_duplicates(subset=["shop_id"], keep="last") \
                    if not df_shops_all.empty else pd.DataFrame()
    df_vouchers_all = safe_concat(all_vouchers)
    df_vouchers   = df_vouchers_all.drop_duplicates(subset=["promotion_id"], keep="last") \
                    if not df_vouchers_all.empty else pd.DataFrame()

    # Ghi CSV (upsert nếu file đã tồn tại từ batch trước)
    save_csv(df_products,   STAGING_DIR, "products",   dedup_col="item_id")
    save_csv(df_models,     STAGING_DIR, "models",     dedup_col="model_id")
    save_csv(df_attributes, STAGING_DIR, "attributes")
    save_csv(df_shops,      STAGING_DIR, "shops",      dedup_col="shop_id")
    save_csv(df_vouchers,   STAGING_DIR, "vouchers",   dedup_col="promotion_id")

    df_full = build_mart(df_products, df_models, df_attributes, df_shops)
    save_csv(df_full, MART_DIR, "products_full", dedup_col="item_id")

    # ── SUMMARY ──
    print("\n📁 Output:")
    print(f"   {STAGING_CLEAN_DIR}/   ← {ok} file JSON đã clean")
    for folder in [STAGING_DIR, MART_DIR]:
        for fname in sorted(os.listdir(folder)):
            if fname.endswith(".csv"):
                fpath2 = os.path.join(folder, fname)
                rows = len(pd.read_csv(fpath2))
                print(f"   {fpath2}  ({rows} dòng)")


# ───────────────────────────── CLI ─────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Shopee Data Cleaning Pipeline — Batch Mode",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
Ví dụ:
  python clean_data.py                          # batch toàn bộ data/raw/*.json
  python clean_data.py --input data/raw/x.json  # chỉ 1 file
  python clean_data.py --json-only              # chỉ clean JSON, không ra CSV
        """
    )
    parser.add_argument("--input", "-i", default=None,
                        help="Xử lý 1 file cụ thể thay vì toàn bộ data/raw/")
    parser.add_argument("--json-only", action="store_true",
                        help="Chỉ clean JSON, không split ra CSV")
    args = parser.parse_args()
    main(input_path=args.input, json_only=args.json_only)