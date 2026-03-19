import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.data_warehouse.sync_duckdb_to_bq import sync_raw_to_bq

if __name__ == "__main__":
    ok = sync_raw_to_bq()
    sys.exit(0 if ok else 1)
