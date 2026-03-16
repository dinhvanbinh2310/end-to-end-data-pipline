import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(_PROJECT_ROOT / ".env")


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def get_warehouse_config() -> dict:
    config_path = _project_root() / "config" / "pipeline.yaml"
    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    wh = cfg.get("warehouse", {})
    project_id = os.getenv("BQ_PROJECT_ID") or wh.get("project_id", "my-sandbox-project")
    dataset = os.getenv("BQ_DATASET") or wh.get("dataset", "shopee_warehouse")

    return {
        "project_id": project_id,
        "dataset": dataset,
    }
