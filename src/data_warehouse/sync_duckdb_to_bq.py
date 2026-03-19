import os
import tempfile
from pathlib import Path

import duckdb
import pandas as pd

from google.cloud import bigquery

from .bq_client import get_bq_client
from .config import get_warehouse_config


def sync_raw_to_bq(duck_path: str | Path | None = None):
    cfg = get_warehouse_config()
    root = Path(__file__).resolve().parent.parent.parent

    if duck_path is None:
        duck_path = root / "data" / "tiki_scraped_data_raw.duckdb"
    else:
        duck_path = Path(duck_path)

    if not duck_path.exists():
        print(f"[!] Khong tim thay DuckDB: {duck_path}")
        return False

    con = duckdb.connect(str(duck_path), read_only=True)
    try:
        tables = con.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'scraped_raw_items_v2'"
        ).fetchone()[0]
        if not tables:
            print("[!] Bang scraped_raw_items_v2 chua ton tai.")
            return False
        df = con.execute("SELECT * FROM scraped_raw_items_v2").fetchdf()
    finally:
        con.close()

    if df.empty:
        print("[!] Bang rong, khong co du lieu de sync.")
        return False

    client = get_bq_client()
    table_id = f"{cfg['project_id']}.{cfg['dataset']}.scraped_raw_items_v2"

    try:
        client.get_dataset(f"{cfg['project_id']}.{cfg['dataset']}")
    except Exception:
        client.create_dataset(cfg["dataset"], exists_ok=True)

    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.CSV,
        skip_leading_rows=1,
        autodetect=True,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        df.to_csv(f.name, index=False)
        path = f.name

    try:
        with open(path, "rb") as fp:
            job = client.load_table_from_file(fp, table_id, job_config=job_config)
        job.result()
    finally:
        os.remove(path)

    print(f"[+] Sync OK: {len(df)} rows -> {table_id}")
    return True


if __name__ == "__main__":
    sync_raw_to_bq()
