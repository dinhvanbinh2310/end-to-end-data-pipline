import sys
from pathlib import Path
import time
import schedule

sys.path.insert(0, str(Path(__file__).parent / "src" / "scraper-services"))

from tiki_scraper import scrape_tiki

KEYWORDS = ["áo thun nam", "điện thoại iphone", "giày thể thao nam", 
            "laptop", "mỹ phẩm", "đồng hồ nam", "túi xách nữ"]

def job():
    demo = "--demo" in sys.argv
    pages = 2 if demo else 5  # 5 trang x 50 sp = 250 sp/keyword
    output_dir = str(Path(__file__).parent / "data")

    print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] BẮT ĐẦU CHU KỲ CÀO DỮ LIỆU ĐỊNH KỲ...")
    
    for kw in KEYWORDS:
        print(f"\n---> Đang cào dữ liệu cho từ khóa: '{kw}' | Pages: {pages} | Demo: {demo}")
        try:
            scrape_tiki(kw, pages, output_dir)
        except Exception as e:
            print(f"[!] Lỗi khi cào '{kw}': {e}")
            
    print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] HOÀN THÀNH TOÀN BỘ CHU KỲ. Đang ngủ chờ 1 tiếng nữa...\n")

if __name__ == "__main__":
    # Chạy lần đầu tiên ngay lập tức khi mở script
    job()
    
    # Lên lịch chạy định kỳ mỗi 1 giờ
    schedule.every(1).hours.do(job)
    
    # Vòng lặp vô hạn giữ cho script hoạt động để kiểm tra lịch
    while True:
        schedule.run_pending()
        time.sleep(1)