# Shopee Purchase Pipeline

Pipeline phân tích hành vi mua hàng trên Shopee: crawl dữ liệu từ API, lưu raw vào DuckDB.

## Cấu trúc

```
├── config/
│   └── pipeline.yaml     # cấu hình Shopee API, đường dẫn
├── src/
│   └── crawler.py        # logic crawl + lưu DuckDB
├── run_crawl.py          # entry point
├── requirements.txt
└── data/
    └── shopee.duckdb     # database (tự tạo khi chạy)
```

## Cài đặt

```
> pip install -r requirements.txt
```

Nếu dùng nhiều Python (ServBay, Miniconda...):

```
> python -m pip install -r requirements.txt
```

BigQuery (nếu cần):

```
> pip install google-cloud-bigquery
> python -m pip install google-cloud-bigquery
```

## Chạy

```
> python run_crawl.py
> python run_crawl.py laptop 2025-03-12
> python run_crawl.py --demo
> python run clean
```

## Cấu hình

`config/pipeline.yaml`: `shopee.base_url`, `shopee.limit_per_page`, `paths.duckdb` (override: `DUCKDB_PATH`).

## Truy vấn DuckDB

```
> python -c "import duckdb; c=duckdb.connect('data/shopee.duckdb'); print(c.execute('SELECT COUNT(*), load_date FROM raw_products GROUP BY load_date').fetchall())"
```
## Lệnh lấy  crawl mẫu 
```
> python run_crawl.py "áo thun nam" 2
```