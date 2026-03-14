import duckdb
import os
from pathlib import Path

def add_danh_muc_column(db_filename="tiki_scraped_data_raw.duckdb"):
    """
    Migration: Bổ sung cột 'danh_muc' vào bảng scraped_raw_items_v2.
    Chạy file này 1 lần sau khi đã có bảng từ create_raw_table.py.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = Path(script_dir).parent.parent
    db_path = os.path.join(project_root, "data", db_filename)

    if not os.path.exists(db_path):
        print(f"[!] Lỗi: Không tìm thấy file database '{db_path}'.")
        print("[!] Vui lòng chạy create_raw_table.py trước.")
        return

    print(f"[*] Đang chạy Migration thêm cột 'danh_muc': {db_path}")

    try:
        con = duckdb.connect(db_path)

        # Kiểm tra xem cột danh_muc đã tồn tại chưa
        cols = [row[0] for row in con.execute("DESCRIBE scraped_raw_items_v2").fetchall()]

        if "danh_muc" in cols:
            print("[+] Cột 'danh_muc' đã tồn tại. Bỏ qua migration này.")
        else:
            con.execute("ALTER TABLE scraped_raw_items_v2 ADD COLUMN danh_muc VARCHAR")
            print("[+] Đã thêm cột 'danh_muc' vào bảng scraped_raw_items_v2 thành công!")

        # Kiểm tra cấu trúc bảng sau migration
        print("\n[*] Cấu trúc bảng hiện tại:")
        for row in con.execute("DESCRIBE scraped_raw_items_v2").fetchall():
            print(f"    {row[0]:20s} {row[1]}")

        con.close()
        print("\n[+] Migration hoàn tất. Sẵn sàng cào dữ liệu theo danh mục.")

    except Exception as e:
        print(f"[!] Lỗi khi chạy Migration: {e}")

if __name__ == "__main__":
    add_danh_muc_column("tiki_scraped_data_raw.duckdb")
