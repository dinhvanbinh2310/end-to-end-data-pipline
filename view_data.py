import duckdb
import json
import os
from pathlib import Path
from dotenv import load_dotenv

def view_data(db_filename: str | None = None, limit=1):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    load_dotenv(os.path.join(script_dir, ".env"))

    if db_filename is None:
        env_path = os.getenv("DUCKDB_PATH")
        if env_path:
            db_path = env_path if os.path.isabs(env_path) else os.path.join(script_dir, env_path)
        else:
            db_path = os.path.join(script_dir, "data", "tiki_scraped_data_raw.duckdb")
    else:
        if os.path.isabs(db_filename) or "/" in db_filename or "\\" in db_filename:
            db_path = db_filename if os.path.isabs(db_filename) else os.path.join(script_dir, db_filename)
        else:
            db_path = os.path.join(script_dir, "data", db_filename)

    if not os.path.exists(db_path):
        print(f"[!] Lỗi: Không tìm thấy file dữ liệu '{db_path}'.")
        print("[!] Bạn cần chạy file run_crawl.py ít nhất 1 lần để có dữ liệu mới.")
        return
        
    try:
        print(f"[*] Đang đọc dữ liệu từ: {db_filename}\n")
        con = duckdb.connect(db_path)
        
        # Xem tổng số sản phẩm
        total_rows = con.execute("SELECT COUNT(*) FROM scraped_raw_items_v2").fetchone()[0]
        print(f"-> Tổng cộng có: {total_rows} sản phẩm trong Database.\n")
        
        if total_rows == 0:
            print("[!] Chưa có dữ liệu nào. Bạn cần chạy run_crawl.py trước.")
            con.close()
            return

        # Xem 1 sản phẩm mẫu
        print(f"-> Dưới đây là 1 sản phẩm mẫu:\n")
        row = con.execute("""
            SELECT thoi_diem, nen_tang, ten_san_pham, id_product, danh_muc, du_lieu
            FROM scraped_raw_items_v2 LIMIT 1
        """).fetchone()
        
        thoi_diem, nen_tang, ten_san_pham, id_product, danh_muc, du_lieu = row
        print(f"  Thời điểm : {thoi_diem}")
        print(f"  Nền tảng  : {nen_tang}")
        print(f"  Danh mục  : {danh_muc}")
        print(f"  Tên SP    : {ten_san_pham}")
        print(f"  ID Product: {id_product}")
        print(f"\n  [du_lieu - JSON thô]:")
        # du_lieu có thể là str hoặc dict tùy DuckDB driver
        if isinstance(du_lieu, str):
            parsed = json.loads(du_lieu)
        else:
            parsed = du_lieu
        print(json.dumps(parsed, indent=4, ensure_ascii=False))
        
        print("\n" + "="*50)
        print("Dữ liệu JSON raw rất lớn, bạn nên phân tích bằng Pandas sau này.")
        
        con.close()
        
    except Exception as e:
        print(f"[!] Có lỗi kết nối database: {e}")

if __name__ == "__main__":
    import sys
    db_file = sys.argv[1] if len(sys.argv) > 1 else "tiki_scraped_data_raw.duckdb"
    view_data(db_file)
