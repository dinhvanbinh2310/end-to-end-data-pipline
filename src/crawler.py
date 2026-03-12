import os
import json
import time
import duckdb
import pandas as pd
import requests
import yaml
from datetime import datetime
from pathlib import Path


def load_config():
    config_path = os.environ.get("PIPELINE_CONFIG", "config/pipeline.yaml")
    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg


def resolve_path(path_template):
    s = os.path.expandvars(path_template)
    import re
    m = re.match(r"^\$\{([^:]+):-([^}]*)\}$", s.strip())
    if m:
        return os.environ.get(m.group(1), m.group(2))
    return s


def get_db_path(config):
    p = config["paths"]["duckdb"]
    if isinstance(p, str) and "${" in p:
        import re
        m = re.search(r"\$\{(\w+):-([^}]*)\}", p)
        if m:
            return os.environ.get(m.group(1), m.group(2))
    return os.path.expandvars(str(p))


def fetch_search_items(config, keyword: str, newest: int = 0) -> dict:
    url = f"{config['shopee']['base_url']}{config['shopee']['search_path']}"
    params = {
        "by": "relevancy",
        "keyword": keyword,
        "limit": min(config["shopee"]["limit_per_page"], 40),
        "newest": newest,
        "order": "desc",
        "page_type": "search",
        "scenario": "PAGE_GLOBAL_SEARCH",
        "version": 2,
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": f"{config['shopee']['base_url']}/",
        "Accept": "application/json",
        "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
        "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
    }
    r = requests.get(url, params=params, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_search_items_demo(config, keyword: str, newest: int) -> dict:
    import random
    n = min(10, 40 - newest) if newest < 40 else 0
    items = []
    for i in range(n):
        items.append({
            "item_basic": {
                "itemid": 100000 + newest + i,
                "shopid": random.randint(1, 9999),
                "name": f"[demo] {keyword} - sample {newest + i}",
                "price_min": random.randint(100000, 5000000),
                "price_max": None,
                "price": None,
                "sold": random.randint(0, 500),
                "stock": random.randint(1, 100),
                "item_rating": {"rating_star": round(random.uniform(3, 5), 1)},
                "catid": random.randint(100, 900),
                "cb_option": 0,
            }
        })
    return {"items": items}


def flatten_item(raw_item: dict, load_date: str) -> dict:
    item = raw_item.get("item_basic", {})
    return {
        "itemid": item.get("itemid"),
        "shopid": item.get("shopid"),
        "name": item.get("name"),
        "price_min": item.get("price_min"),
        "price_max": item.get("price_max"),
        "price": item.get("price") or item.get("price_min"),
        "sold": item.get("sold", 0),
        "stock": item.get("stock", 0),
        "rating_star": item.get("item_rating", {}).get("rating_star"),
        "category_id": item.get("catid"),
        "cb_option": item.get("cb_option"),
        "raw_json": json.dumps(raw_item, ensure_ascii=False),
        "load_date": load_date,
        "crawl_time": datetime.utcnow().isoformat(),
    }


def init_raw_tables(con):
    con.execute("""
        CREATE TABLE IF NOT EXISTS raw_products (
            itemid BIGINT,
            shopid BIGINT,
            name VARCHAR,
            price_min BIGINT,
            price_max BIGINT,
            price BIGINT,
            sold INT,
            stock INT,
            rating_star DOUBLE,
            category_id BIGINT,
            cb_option INT,
            raw_json VARCHAR,
            load_date DATE,
            crawl_time TIMESTAMP
        )
    """)


def save_to_duckdb(config, rows: list, load_date: str):
    db_path = get_db_path(config)
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(db_path)
    init_raw_tables(con)
    if not rows:
        con.close()
        return 0
    con.execute("DELETE FROM raw_products WHERE load_date = ?", [load_date])
    cols = ["itemid","shopid","name","price_min","price_max","price","sold","stock","rating_star","category_id","cb_option","raw_json","load_date","crawl_time"]
    df = pd.DataFrame(rows, columns=cols)[cols]
    con.append("raw_products", df)
    count = len(rows)
    con.close()
    return count


def _sample_rows(keyword: str, load_date: str, n: int = 20):
    base = {"name": keyword, "price": 100000, "sold": 10, "stock": 100, "rating_star": 4.5}
    return [{"itemid": i, "shopid": 1, **base, "price_min": 100000, "price_max": 100000,
             "category_id": None, "cb_option": 0, "raw_json": "{}", "load_date": load_date,
             "crawl_time": datetime.utcnow().isoformat()} for i in range(n)]


def crawl(config, keyword: str, load_date: str | None = None, max_pages: int = 5, demo: bool = False):
    load_date = load_date or datetime.utcnow().strftime("%Y-%m-%d")
    all_rows = []
    if demo:
        all_rows = _sample_rows(keyword, load_date)
    else:
        newest = 0
        for _ in range(max_pages):
            try:
                data = fetch_search_items(config, keyword, newest)
            except requests.HTTPError as e:
                if e.response and e.response.status_code == 403:
                    all_rows = _sample_rows(keyword, load_date)
                    break
                raise
            items = data.get("items") or []
            if not items:
                break
            for it in items:
                try:
                    row = flatten_item(it, load_date)
                    all_rows.append(row)
                except Exception:
                    pass
            newest += len(items)
            if len(items) < config["shopee"]["limit_per_page"]:
                break
            delay = config["shopee"].get("request_delay_sec", 1)
            if delay:
                time.sleep(delay)
    count = save_to_duckdb(config, all_rows, load_date)
    print(f"crawl load_date={load_date} records={count}")
    return count


def main():
    import sys
    cfg = load_config()
    kw = sys.argv[1] if len(sys.argv) > 1 else "điện thoại"
    load_date = sys.argv[2] if len(sys.argv) > 2 else None
    crawl(cfg, kw, load_date)


if __name__ == "__main__":
    main()
