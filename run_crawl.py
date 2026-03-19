import sys
from pathlib import Path
import time
import argparse

sys.path.insert(0, str(Path(__file__).parent / "src" / "scraper-services"))

from tiki_scraper import scrape_tiki, sync_prices_from_existing

CATEGORIES = {
    "Áo":           ["áo thun nam", "áo sơ mi nam", "áo khoác nữ"],
    "Quần":         ["quần jean nam", "quần tây nữ", "quần short nam"],
    "Điện thoại":   ["điện thoại iphone", "samsung galaxy", "điện thoại xiaomi"],
    "Giày":         ["giày thể thao nam", "giày cao gót nữ", "giày sneaker"],
    "Dép":          ["dép lào nam", "dép sandal nữ"],
    "Laptop":       ["laptop gaming", "macbook", "laptop văn phòng"],
    "Mỹ phẩm":      ["son môi", "kem dưỡng da", "serum dưỡng da"],
    "Đồng hồ":      ["đồng hồ nam", "đồng hồ nữ thời trang"],
    "Túi xách":     ["túi xách nữ", "ba lô nam", "ví da nam"],
    "Phụ kiện":     ["tai nghe bluetooth", "sạc dự phòng", "ốp lưng điện thoại"],
}

def run_cycle(mode: str, pages: int, output_dir: str, max_items: int | None = None):
    print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] BẮT ĐẦU CHU KỲ CÀO DỮ LIỆU ĐỊNH KỲ...")

    if mode == "existing":
        try:
            sync_limit = max_items if max_items is not None else 100
            sync_prices_from_existing(output_dir=output_dir, max_items=sync_limit)
        except Exception as e:
            print(f"[!] Lỗi khi sync sản phẩm cũ: {e}")
    else:
        for danh_muc, keywords in CATEGORIES.items():
            for kw in keywords:
                print(f"\n---> Danh mục: [{danh_muc}] | Từ khóa: '{kw}' | Pages: {pages}")
                try:
                    # dedupe_hours=0 để mỗi lần cào đều tạo snapshot mới.
                    scrape_tiki(kw, pages, output_dir, danh_muc=danh_muc, page_limit=50, dedupe_hours=0)
                except Exception as e:
                    print(f"[!] Lỗi khi cào '{kw}': {e}")
            
    print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] HOÀN THÀNH TOÀN BỘ CHU KỲ.\n")


def parse_args():
    parser = argparse.ArgumentParser(description="Chạy crawler định kỳ 24/24.")
    parser.add_argument(
        "--mode",
        choices=["existing", "keyword"],
        default="existing",
        help="existing: sync giá từ sản phẩm cũ, keyword: cào mới theo danh sách từ khóa",
    )
    parser.add_argument("--pages", type=int, default=5, help="Số trang khi chạy mode keyword")
    parser.add_argument("--demo", action="store_true", help="Mode demo: pages=1")
    parser.add_argument("--once", action="store_true", help="Chỉ chạy 1 chu kỳ rồi thoát")
    parser.add_argument("--interval-hours", type=float, default=1.0, help="Khoảng thời gian giữa các chu kỳ")
    parser.add_argument("--max-items", type=int, default=None, help="Giới hạn số item refresh trong mode existing")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    pages = 1 if args.demo else args.pages
    output_dir = str(Path(__file__).parent / "data")

    run_cycle(mode=args.mode, pages=pages, output_dir=output_dir, max_items=args.max_items)
    if args.once:
        raise SystemExit(0)

    interval_seconds = max(60, int(args.interval_hours * 3600))
    while True:
        print(f"[*] Chờ {args.interval_hours} giờ trước chu kỳ tiếp theo...")
        time.sleep(interval_seconds)
        run_cycle(mode=args.mode, pages=pages, output_dir=output_dir, max_items=args.max_items)