import os

from google.cloud import bigquery

from .config import get_warehouse_config


def get_bq_client() -> bigquery.Client:
    cfg = get_warehouse_config()
    credentials = None
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if creds_path:
        from google.oauth2 import service_account
        credentials = service_account.Credentials.from_service_account_file(creds_path)
    return bigquery.Client(
        project=cfg["project_id"],
        credentials=credentials,
    )
