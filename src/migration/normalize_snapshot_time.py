import argparse
import shutil
from datetime import datetime
from pathlib import Path

import duckdb

TABLE_NAME = "scraped_raw_items_v2"


def normalize_snapshot_time(db_path: Path, gap_seconds: int = 120, make_backup: bool = True) -> None:
    if not db_path.exists():
        raise FileNotFoundError(f"Khong tim thay DB: {db_path}")

    if make_backup:
        backup_name = f"{db_path.stem}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}{db_path.suffix}"
        backup_path = db_path.with_name(backup_name)
        shutil.copy2(db_path, backup_path)
        print(f"[*] Da tao backup: {backup_path}")

    con = duckdb.connect(str(db_path))
    try:
        table_exists = con.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?",
            [TABLE_NAME],
        ).fetchone()
        if not table_exists or not table_exists[0]:
            print(f"[!] Khong tim thay bang {TABLE_NAME}")
            return

        stats_before_row = con.execute(
            f"""
            SELECT
                COUNT(*) AS total_rows,
                COUNT(DISTINCT thoi_diem) AS distinct_times
            FROM {TABLE_NAME}
            WHERE TRY_CAST(thoi_diem AS TIMESTAMP) IS NOT NULL
            """
        ).fetchone()
        stats_before = stats_before_row if stats_before_row is not None else (0, 0)
        print(f"[*] Truoc khi chuan hoa: total_rows={stats_before[0]}, distinct_thoi_diem={stats_before[1]}")

        normalized_cte = f"""
            WITH ordered AS (
                SELECT
                    rowid AS rid,
                    TRY_CAST(thoi_diem AS TIMESTAMP) AS ts,
                    LAG(TRY_CAST(thoi_diem AS TIMESTAMP)) OVER (
                        ORDER BY TRY_CAST(thoi_diem AS TIMESTAMP), rowid
                    ) AS prev_ts
                FROM {TABLE_NAME}
                WHERE TRY_CAST(thoi_diem AS TIMESTAMP) IS NOT NULL
            ),
            marks AS (
                SELECT
                    rid,
                    ts,
                    CASE
                        WHEN prev_ts IS NULL THEN 1
                        WHEN date_diff('second', prev_ts, ts) > {int(gap_seconds)} THEN 1
                        ELSE 0
                    END AS new_batch
                FROM ordered
            ),
            grouped AS (
                SELECT
                    rid,
                    ts,
                    SUM(new_batch) OVER (
                        ORDER BY ts, rid
                        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                    ) AS batch_id
                FROM marks
            ),
            normalized AS (
                SELECT
                    rid,
                    strftime(MIN(ts) OVER (PARTITION BY batch_id), '%Y-%m-%d %H:%M:%S') AS thoi_diem_new
                FROM grouped
            )
        """

        changed_rows_row = con.execute(
            f"""
            {normalized_cte}
            SELECT COUNT(*)
            FROM {TABLE_NAME} t
            JOIN normalized n ON t.rowid = n.rid
            WHERE COALESCE(t.thoi_diem, '') <> COALESCE(n.thoi_diem_new, '')
            """
        ).fetchone()
        changed_rows = int(changed_rows_row[0]) if changed_rows_row is not None else 0

        update_sql = f"""
            {normalized_cte}
            UPDATE {TABLE_NAME} t
            SET thoi_diem = n.thoi_diem_new
            FROM normalized n
            WHERE t.rowid = n.rid
              AND COALESCE(t.thoi_diem, '') <> COALESCE(n.thoi_diem_new, '')
        """

        con.execute("BEGIN")
        con.execute(update_sql)
        con.execute("COMMIT")

        stats_after_row = con.execute(
            f"""
            SELECT
                COUNT(*) AS total_rows,
                COUNT(DISTINCT thoi_diem) AS distinct_times
            FROM {TABLE_NAME}
            WHERE TRY_CAST(thoi_diem AS TIMESTAMP) IS NOT NULL
            """
        ).fetchone()
        stats_after = stats_after_row if stats_after_row is not None else (0, 0)
        print(f"[*] Da cap nhat {changed_rows} dong")
        print(f"[*] Sau khi chuan hoa: total_rows={stats_after[0]}, distinct_thoi_diem={stats_after[1]}")
    finally:
        con.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Chuan hoa thoi_diem theo batch crawl.")
    parser.add_argument(
        "--db",
        type=str,
        default="data/tiki_scraped_data_raw.duckdb",
        help="Duong dan toi file DuckDB",
    )
    parser.add_argument(
        "--gap-seconds",
        type=int,
        default=120,
        help="Khoang cach giay de tach batch moi",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Tat tao file backup truoc khi update",
    )

    args = parser.parse_args()
    db_path = Path(args.db).resolve()
    normalize_snapshot_time(db_path=db_path, gap_seconds=int(args.gap_seconds), make_backup=not args.no_backup)


if __name__ == "__main__":
    main()
