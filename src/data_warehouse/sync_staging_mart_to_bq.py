from pathlib import Path

from google.cloud import bigquery

from .bq_client import get_bq_client
from .config import get_warehouse_config

FILES = [
    ("data/staging/products.parquet", "staging_products"),
    ("data/mart/products_full.parquet", "mart_products_full"),
]


def sync_staging_mart_to_bq(root: Path | None = None):
    root = root or Path(__file__).resolve().parent.parent.parent
    cfg = get_warehouse_config()
    client = get_bq_client()
    dataset_ref = f"{cfg['project_id']}.{cfg['dataset']}"

    try:
        client.get_dataset(dataset_ref)
    except Exception:
        client.create_dataset(cfg["dataset"], exists_ok=True)

    ok = True
    for rel_path, table_name in FILES:
        path = root / rel_path
        if not path.exists():
            print(f"[!] Khong tim thay: {path}")
            ok = False
            continue

        table_id = f"{dataset_ref}.{table_name}"
        job_config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.PARQUET,
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        )
        with open(path, "rb") as f:
            job = client.load_table_from_file(f, table_id, job_config=job_config)
        job.result()
        rows = job.output_rows or 0
        print(f"[+] Sync OK: {path.name} -> {table_id} ({rows} dong)")
    return ok


if __name__ == "__main__":
    sync_staging_mart_to_bq()
