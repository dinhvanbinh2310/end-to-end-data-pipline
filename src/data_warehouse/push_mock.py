import os
import tempfile
from datetime import datetime

import pandas as pd

from google.cloud import bigquery

from .bq_client import get_bq_client
from .config import get_warehouse_config


def push_mock_product_dim():
    cfg = get_warehouse_config()
    client = get_bq_client()

    dataset_id = cfg["dataset"]
    table_id = "product_dim"
    full_id = f"{cfg['project_id']}.{dataset_id}.{table_id}"

    try:
        client.get_dataset(f"{cfg['project_id']}.{dataset_id}")
    except Exception:
        client.create_dataset(dataset_id, exists_ok=True)

    df = pd.DataFrame([
        {"product_id": "p001", "product_name": "Ao thun nam", "category": "Thoi trang", "price": 199000, "load_date": datetime.now().isoformat()},
        {"product_id": "p002", "product_name": "Quan jean", "category": "Thoi trang", "price": 350000, "load_date": datetime.now().isoformat()},
        {"product_id": "p003", "product_name": "Laptop gaming", "category": "Dien tu", "price": 25000000, "load_date": datetime.now().isoformat()},
        {"product_id": "p004", "product_name": "Tai nghe Bluetooth", "category": "Phu kien", "price": 450000, "load_date": datetime.now().isoformat()},
        {"product_id": "p005", "product_name": "Giay sneaker", "category": "Giay dep", "price": 890000, "load_date": datetime.now().isoformat()},
    ])

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        df.to_csv(f.name, index=False)
        path = f.name

    try:
        job_config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.CSV,
            skip_leading_rows=1,
            autodetect=True,
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        )
        with open(path, "rb") as fp:
            job = client.load_table_from_file(fp, full_id, job_config=job_config)
        job.result()
    finally:
        os.remove(path)

    print(f"[+] Pushed {len(df)} rows to {full_id}")
    print(f"[+] Dashboard: https://console.cloud.google.com/bigquery?project={cfg['project_id']}")


if __name__ == "__main__":
    push_mock_product_dim()
