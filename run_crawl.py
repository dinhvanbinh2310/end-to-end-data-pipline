import sys
from pathlib import Path
import time
import argparse

sys.path.insert(0, str(Path(__file__).parent / "src" / "scraper-services"))

from tiki_scraper import scrape_tiki, refresh_existing_tiki_items

KEYWORDS = ["áo thun nam", "điện thoại iphone", "giày thể thao nam", 
            "laptop", "mỹ phẩm", "đồng hồ nam", "túi xách nữ"]

def run_cycle(mode: str, pages: int, output_dir: str, max_items: int | None = None):
    print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] BẮT ĐẦU CHU KỲ CÀO DỮ LIỆU ĐỊNH KỲ...")

    if mode == "existing":
        try:
            ok = refresh_existing_tiki_items(output_dir=output_dir, max_items=max_items)
            if not ok:
                print("[!] Chu kỳ refresh thất bại hoặc không có dữ liệu để refresh.")
        except Exception as e:
            print(f"[!] Lỗi khi refresh sản phẩm hiện có: {e}")
    else:
        for kw in KEYWORDS:
            print(f"\n---> Đang cào dữ liệu cho từ khóa: '{kw}' | Pages: {pages}")
            try:
                scrape_tiki(kw, pages, output_dir)
            except Exception as e:
                print(f"[!] Lỗi khi cào '{kw}': {e}")
            
    print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] HOÀN THÀNH TOÀN BỘ CHU KỲ.\n")


def parse_args():
    parser = argparse.ArgumentParser(description="Chạy crawler định kỳ 24/24.")
    parser.add_argument(
        "--mode",
        choices=["existing", "keyword"],
        default="existing",
        help="existing: chỉ refresh item hiện có trong DB, keyword: cào lại theo danh sách từ khóa",
    )
    parser.add_argument("--pages", type=int, default=5, help="Số trang khi chạy mode keyword")
    parser.add_argument("--demo", action="store_true", help="Mode demo: pages=2")
    parser.add_argument("--once", action="store_true", help="Chỉ chạy 1 chu kỳ rồi thoát")
    parser.add_argument("--interval-hours", type=float, default=1.0, help="Khoảng thời gian giữa các chu kỳ")
    parser.add_argument("--max-items", type=int, default=None, help="Giới hạn số item refresh trong mode existing")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    pages = 2 if args.demo else args.pages
    output_dir = str(Path(__file__).parent / "data")

    run_cycle(mode=args.mode, pages=pages, output_dir=output_dir, max_items=args.max_items)
    if args.once:
        raise SystemExit(0)

    interval_seconds = max(60, int(args.interval_hours * 3600))
    while True:
        print(f"[*] Chờ {args.interval_hours} giờ trước chu kỳ tiếp theo...")
        time.sleep(interval_seconds)
        run_cycle(mode=args.mode, pages=pages, output_dir=output_dir, max_items=args.max_items)