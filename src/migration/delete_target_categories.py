from datetime import datetime
from pathlib import Path
import shutil

import duckdb

DB_PATH = Path("data/tiki_scraped_data_raw.duckdb")
TABLE_NAME = "scraped_raw_items_v2"
TARGET_CATEGORIES = [
    "dien_thoai",
    "laptop",
    "giay",
    "ao",
    "quan",
    "my_pham",
    "dong_ho",
    "tui_xach",
    "phu_kien",
    "do_gia_dung",
]


def main() -> None:
    db_path = DB_PATH.resolve()
    if not db_path.exists():
        raise FileNotFoundError(f"Khong tim thay DB: {db_path}")

    backup_path = db_path.with_name(
        f"{db_path.stem}.pre_delete_10cats_{datetime.now().strftime('%Y%m%d_%H%M%S')}{db_path.suffix}"
    )
    shutil.copy2(db_path, backup_path)
    print(f"[*] Da tao backup: {backup_path}")

    placeholders = ",".join(["?"] * len(TARGET_CATEGORIES))

    with duckdb.connect(str(db_path)) as con:
        before_row = con.execute(
            f"SELECT COUNT(*) FROM {TABLE_NAME} WHERE danh_muc IN ({placeholders})",
            TARGET_CATEGORIES,
        ).fetchone()
        before_count = int(before_row[0]) if before_row is not None else 0

        con.execute(
            f"DELETE FROM {TABLE_NAME} WHERE danh_muc IN ({placeholders})",
            TARGET_CATEGORIES,
        )

        after_row = con.execute(
            f"SELECT COUNT(*) FROM {TABLE_NAME} WHERE danh_muc IN ({placeholders})",
            TARGET_CATEGORIES,
        ).fetchone()
        after_count = int(after_row[0]) if after_row is not None else 0

        total_row = con.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()
        total_left = int(total_row[0]) if total_row is not None else 0

    print(f"[*] So dong thuoc 10 danh muc truoc khi xoa: {before_count}")
    print(f"[*] So dong thuoc 10 danh muc sau khi xoa: {after_count}")
    print(f"[*] Tong so dong con lai trong bang: {total_left}")


if __name__ == "__main__":
    main()
