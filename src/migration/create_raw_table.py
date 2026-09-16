import duckdb
import os
from pathlib import Path
from dotenv import load_dotenv

def create_raw_table(db_filename: str | None = None):
    """
    Tạo bảng dữ liệu thô (raw) theo đúng chuẩn cấu trúc của Leader.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = Path(script_dir).parent.parent
    load_dotenv(project_root / ".env")

    if db_filename is None:
        env_path = os.getenv("DUCKDB_PATH")
        if env_path:
            p = Path(env_path)
            db_path = str(p if p.is_absolute() else (project_root / p).resolve())
        else:
            db_path = str(project_root / "data" / "tiki_scraped_data_raw.duckdb")
    else:
        p = Path(db_filename)
        if p.is_absolute():
            db_path = str(p)
        elif "/" in db_filename or "\\" in db_filename:
            db_path = str((project_root / p).resolve())
        else:
            output_dir = os.path.join(project_root, "data")
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            db_path = os.path.join(output_dir, db_filename)

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
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
                id_product BIGINT,          -- ID của sản phẩm trên nền tảng đó
                danh_muc VARCHAR,
                tu_khoa VARCHAR,
                gia_hien_tai BIGINT,
                gia_goc BIGINT,
                diem_danh_gia DOUBLE,
                luot_mua BIGINT,
                product_url VARCHAR,
                kieu_cao VARCHAR
            )
        """)

        # Đảm bảo các cột mới luôn tồn tại cho DB cũ.
        cols = {row[0] for row in con.execute("DESCRIBE scraped_raw_items_v2").fetchall()}
        required = {
            "danh_muc": "VARCHAR",
            "tu_khoa": "VARCHAR",
            "gia_hien_tai": "BIGINT",
            "gia_goc": "BIGINT",
            "diem_danh_gia": "DOUBLE",
            "luot_mua": "BIGINT",
            "product_url": "VARCHAR",
            "kieu_cao": "VARCHAR",
        }
        for col_name, col_type in required.items():
            if col_name not in cols:
                con.execute(f"ALTER TABLE scraped_raw_items_v2 ADD COLUMN {col_name} {col_type}")
        
        # Kiểm tra xem bảng tạo thành công không
        tables = con.execute("SHOW TABLES").fetchall()
        print(f"[+] Hoàn tất! Danh sách các bảng hiện có: {tables}")
        print("[+] Migration thành công. Sẵn sàng cấu hình chạy crawler.")
        
        con.close()
        
    except Exception as e:
        print(f"[!] Lỗi khi chạy Migration: {e}")

if __name__ == "__main__":
    create_raw_table("tiki_scraped_data_raw.duckdb")
