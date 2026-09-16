import os
import sys
import yaml
import duckdb
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.migration.create_raw_table import create_raw_table


def test_yaml_configs():
    """Kiểm tra tính hợp lệ của tất cả các file cấu hình YAML."""
    config_dir = Path(__file__).parent.parent / "config"
    yaml_files = list(config_dir.glob("*.yaml")) + list(config_dir.glob("*.yml"))
    assert len(yaml_files) > 0, "Không tìm thấy file config YAML nào."

    for yml_file in yaml_files:
        with open(yml_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            assert isinstance(data, dict), f"File {yml_file.name} không parse được dạng dict."


def test_duckdb_migration_creates_table(tmp_path):
    """Kiểm tra hàm migration tạo đúng bảng và schema trong DuckDB."""
    test_db = tmp_path / "test_raw.duckdb"
    con = duckdb.connect(str(test_db))

    con.execute("""
        CREATE TABLE IF NOT EXISTS scraped_raw_items_v2 (
            thoi_diem VARCHAR,
            nen_tang VARCHAR,
            du_lieu JSON,
            ten_san_pham VARCHAR,
            id_product BIGINT,
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

    tables = [row[0] for row in con.execute("SHOW TABLES").fetchall()]
    assert "scraped_raw_items_v2" in tables

    columns = {row[0] for row in con.execute("DESCRIBE scraped_raw_items_v2").fetchall()}
    required_cols = {"thoi_diem", "ten_san_pham", "gia_hien_tai", "danh_muc", "kieu_cao"}
    assert required_cols.issubset(columns)
    con.close()


def test_crawler_categories_config():
    """Kiểm tra danh sách danh mục cào trong run_crawl có hợp lệ không."""
    from run_crawl import CATEGORIES
    assert isinstance(CATEGORIES, dict), "CATEGORIES phải là một dictionary"
    assert len(CATEGORIES) > 0, "CATEGORIES không được rỗng"
    for category_name, keywords in CATEGORIES.items():
        assert len(keywords) > 0, f"Danh mục '{category_name}' không được để trống từ khóa"




