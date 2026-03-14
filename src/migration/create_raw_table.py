import duckdb
import os
from pathlib import Path

def create_raw_table(db_filename="tiki_scraped_data_raw.duckdb"):
    """
    Tạo bảng dữ liệu thô (raw) theo đúng chuẩn cấu trúc của Leader.
    """
    
    # Đảm bảo thư mục lưu data tồn tại
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = Path(script_dir).parent.parent
    output_dir = os.path.join(project_root, "data")
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    db_path = os.path.join(output_dir, db_filename)
    
    print(f"[*] Đang thực thi Migration tạo cấu trúc bảng Database: {db_path}")
    
    try:
        con = duckdb.connect(db_path)
        
        # Tạo bảng theo yều cầu (không xóa bảng cũ nếu đã có)
        con.execute("""
            CREATE TABLE IF NOT EXISTS scraped_raw_items_v2 (
                thoi_diem VARCHAR,          -- Thời điểm cào
                nen_tang VARCHAR,           -- Platform (vd: tiki, shopee)
                du_lieu JSON,               -- Toàn bộ JSON trả về từ API
                ten_san_pham VARCHAR,       -- Tên sản phẩm
                id_product BIGINT           -- ID của sản phẩm trên nền tảng đó
            )
        """)
        
        # Kiểm tra xem bảng tạo thành công không
        tables = con.execute("SHOW TABLES").fetchall()
        print(f"[+] Hoàn tất! Danh sách các bảng hiện có: {tables}")
        print("[+] Migration thành công. Sẵn sàng cấu hình chạy crawler.")
        
        con.close()
        
    except Exception as e:
        print(f"[!] Lỗi khi chạy Migration: {e}")

if __name__ == "__main__":
    create_raw_table("tiki_scraped_data_raw.duckdb")
