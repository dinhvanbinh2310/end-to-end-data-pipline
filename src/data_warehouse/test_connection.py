from .bq_client import get_bq_client
from .config import get_warehouse_config


def test():
    cfg = get_warehouse_config()
    client = get_bq_client()
    client.query("SELECT 1").result()
    print(f"[+] BigQuery sandbox OK: {cfg['project_id']}.{cfg['dataset']}")

if __name__ == "__main__":
    test()
