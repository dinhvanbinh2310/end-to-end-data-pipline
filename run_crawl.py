import sys
from pathlib import Path
import time
import schedule

sys.path.insert(0, str(Path(__file__).parent / "src" / "scraper-services"))

from tiki_scraper import scrape_tiki

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

def job():
    demo = "--demo" in sys.argv
    pages = 1 if demo else 3
    output_dir = str(Path(__file__).parent / "data")

    print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] BẮT ĐẦU CHU KỲ CÀO DỮ LIỆU ĐỊNH KỲ...")
    
    for danh_muc, keywords in CATEGORIES.items():
        for kw in keywords:
            print(f"\n---> Danh mục: [{danh_muc}] | Từ khóa: '{kw}' | Pages: {pages}")
            try:
                scrape_tiki(kw, pages, output_dir, danh_muc=danh_muc)
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