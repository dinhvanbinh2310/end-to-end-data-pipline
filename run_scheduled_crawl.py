import argparse
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

BASE_DIR = Path(__file__).resolve().parent
SCRAPER_DIR = BASE_DIR / "src" / "scraper-services"
sys.path.insert(0, str(SCRAPER_DIR))

from tiki_scraper import crawl_new_products  # noqa: E402

VALID_INTERVALS = {5, 10, 20, 30, 60}


def load_config(config_path: Path) -> dict:
    if not config_path.exists():
        raise FileNotFoundError(f"Khong tim thay file config: {config_path}")
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("Config khong hop le: phai la object YAML")
    return data


def normalize_pairs(raw_pairs: object) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    if not isinstance(raw_pairs, list):
        return pairs

    for row in raw_pairs:
        if not isinstance(row, dict):
            continue
        danh_muc = str(row.get("danh_muc", "")).strip()
        tu_khoa = str(row.get("tu_khoa", "")).strip()
        if danh_muc and tu_khoa:
            pairs.append((danh_muc, tu_khoa))
    return pairs


def should_run_now(interval_minutes: int, now_local: datetime) -> bool:
    if interval_minutes == 60:
        return now_local.minute == 0
    return now_local.minute % interval_minutes == 0


def run_once(config_path: Path, tz_name: str, force_run: bool = False) -> int:
    cfg = load_config(config_path)

    enabled = bool(cfg.get("enabled", True))
    if not enabled:
        print("[*] Scheduler dang tat trong config (enabled=false). Bo qua.")
        return 0

    interval_minutes = int(cfg.get("interval_minutes", 5))
    if interval_minutes not in VALID_INTERVALS:
        raise ValueError(f"interval_minutes={interval_minutes} khong hop le. Cho phep: {sorted(VALID_INTERVALS)}")

    quantity = int(cfg.get("quantity", 10))
    output_dir = str(cfg.get("output_dir", "data")).strip() or "data"
    pairs = normalize_pairs(cfg.get("pairs", []))

    if not pairs:
        print("[*] Khong co cap danh_muc-tu_khoa nao trong config. Bo qua.")
        return 0

    tz = ZoneInfo(tz_name)
    now_local = datetime.now(tz)

    if not force_run and not should_run_now(interval_minutes, now_local):
        print(
            f"[*] Chua den moc chay. Bay gio {now_local.strftime('%Y-%m-%d %H:%M:%S %Z')}, "
            f"interval={interval_minutes}p"
        )
        return 0

    print(
        f"[*] Bat dau crawl: {now_local.strftime('%Y-%m-%d %H:%M:%S %Z')} | "
        f"interval={interval_minutes}p | quantity={quantity} | pairs={len(pairs)}"
    )

    total_inserted = 0
    total_requested = 0
    failed_pairs: list[str] = []

    for danh_muc, tu_khoa in pairs:
        try:
            result = crawl_new_products(
                keyword=tu_khoa,
                quantity=quantity,
                output_dir=output_dir,
                danh_muc=danh_muc,
            )
            inserted = int(result.get("inserted", 0))
            requested = int(result.get("requested", quantity))
            total_inserted += inserted
            total_requested += requested
            print(f"[+] {danh_muc} | {tu_khoa}: {inserted}/{requested}")
        except Exception as exc:
            failed_pairs.append(f"{danh_muc}|{tu_khoa}")
            print(f"[!] Loi {danh_muc} | {tu_khoa}: {exc}")

    print(f"[*] Hoan tat: {total_inserted}/{total_requested} record moi.")

    if failed_pairs:
        print("[!] Cac cap bi loi:")
        for pair in failed_pairs:
            print(f"    - {pair}")
        return 1

    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Chay crawl theo config cho GitHub Actions / scheduler")
    parser.add_argument("--config", type=str, default="config/auto_crawl.yaml", help="Duong dan config YAML")
    parser.add_argument("--timezone", type=str, default="Asia/Ho_Chi_Minh", help="Timezone de canh moc phut")
    parser.add_argument("--force-run", action="store_true", help="Bo qua check mốc thoi gian, chay ngay")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    exit_code = run_once(
        config_path=(BASE_DIR / args.config).resolve(),
        tz_name=args.timezone,
        force_run=bool(args.force_run),
    )
    raise SystemExit(exit_code)
