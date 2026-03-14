import duckdb
import json

con = duckdb.connect("data/tiki_scraped_data_raw.duckdb")

rows = con.execute("""
    SELECT ten_san_pham, du_lieu
    FROM scraped_raw_items_v2
    LIMIT 5
""").fetchall()

print("Kiểm tra URL sản phẩm:")
print("="*60)
for row in rows:
    ten = row[0]
    data = json.loads(row[1])
    url_path = data.get("url_path", "")
    full_url = f"https://tiki.vn/{url_path}"
    print(f"Tên : {ten}")
    print(f"URL : {full_url}")
    print("-"*60)

con.close()