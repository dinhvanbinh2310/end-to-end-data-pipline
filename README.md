# Shopee Purchase Pipeline

Pipeline phân tích hành vi mua hàng trên Shopee: crawl dữ liệu từ API, lưu raw vào DuckDB.

## Cấu trúc

```
├── config/
│   └── pipeline.yaml     # cấu hình Shopee API, đường dẫn
├── src/
│   ├── migration/        
│   │   └── create_raw_table.py  # Script tạo cấu trúc bảng chuẩn V2
│   └── crawler.py        # logic crawl + lưu DuckDB
├── run_crawl.py          # entry point
├── requirements.txt
└── data/
    └── shopee.duckdb     # database (tự tạo khi chạy)
```

## Khởi tạo Database (Bắt buộc)

Trước khi chạy cào dữ liệu lần đầu tiên, team cần chạy file Migration để DuckDB thiết lập bảng `scraped_raw_items_v2` với các cột Data chuẩn:

```bash
> python src/migration/create_raw_table.py
```

## Cài đặt

```
> pip install -r requirements.txt
```

Nếu dùng nhiều Python (ServBay, Miniconda...):

```
> python -m pip install -r requirements.txt
```

BigQuery sandbox (không cần billing, dùng ADC):

```
> pip install google-cloud-bigquery
> gcloud auth application-default login
```

Cấu hình `.env`: `BQ_PROJECT_ID`, `BQ_DATASET` (project tạo tại console.cloud.google.com/bigquery)

## Chạy

```
> python run_crawl.py
> python run_crawl.py laptop 2025-03-12
> python run_crawl.py --demo
> python run clean
```

## Chạy clean_data.py
pip install pyarrow  (nếu chưa tải thư viện)

# 1. Chạy mặc định — tự tìm DB ở ../../data/tiki_scraped_data_raw.duckdb
python clean_data.py

# 2. Chỉ định đường dẫn DB cụ thể (nếu chạy từ thư mục khác)
python clean_data.py --db data/tiki_scraped_data_raw.duckdb

# 3. Chỉ đọc 100 bản ghi đầu — dùng để TEST NHANH xem output đúng chưa
python clean_data.py --db data/tiki_scraped_data_raw.duckdb --limit 100


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

## Crawl liên tục 24/24 (1 lần mỗi giờ)

Script `run_crawl.py` đã hỗ trợ chạy liên tục theo chu kỳ.

1. Refresh sản phẩm hiện có trong DB (khuyến nghị):

```
python run_crawl.py --mode existing --interval-hours 1
```

2. Chạy 1 lần để test rồi thoát:

```
python run_crawl.py --mode existing --once
```

3. Nếu muốn cào lại theo danh sách từ khóa:

```
python run_crawl.py --mode keyword --interval-hours 1
```

## Sync DuckDB len BigQuery

Dong bo du lieu tu `data/tiki_scraped_data_raw.duckdb` len BigQuery:

```
python run_sync.py
```

Hoac:

```
python -m src.data_warehouse.sync_duckdb_to_bq
```

Can cau hinh `.env`: `GOOGLE_APPLICATION_CREDENTIALS`, `BQ_PROJECT_ID`, `BQ_DATASET`.

## Xem dữ liệu bằng Streamlit

1. Cài dependencies:

```
python -m pip install -r requirements.txt
```

2. Chạy frontend:

```
streamlit run streamlit_app.py
```

3. Mở trình duyệt tại địa chỉ Streamlit in ra trong terminal (thường là http://localhost:8501).

Frontend sẽ tự động tìm dữ liệu ở một trong hai thư mục:
- `data/`
- `src/data-engine/data/`

Các tab chính:
- Raw: xem file JSON thô và JSON đã clean.
- Staging: xem bảng `products`, `models`, `attributes`, `shops`.
- Mart: xem `products_full.csv`, lọc theo category/shop và tìm kiếm theo thuộc tính bằng dropdown.
- DuckDB: xem bảng trong `data/tiki_scraped_data_raw.duckdb`.

## Sync DuckDB len BigQuery (Cloud)

Dong bo du lieu tu DuckDB local len BigQuery:

```
python run_sync.py
```

Hoac:

```
python -m src.data_warehouse.sync_duckdb_to_bq
```

Can cau hinh `.env`: `GOOGLE_APPLICATION_CREDENTIALS`, `BQ_PROJECT_ID`, `BQ_DATASET`.

## Sync DuckDB len BigQuery

Dong bo du lieu raw tu `data/tiki_scraped_data_raw.duckdb` len BigQuery:

```
python run_sync.py
```

Hoac:

```
python -m src.data_warehouse.sync_duckdb_to_bq
```

Can cau hinh `.env`: `GOOGLE_APPLICATION_CREDENTIALS`, `BQ_PROJECT_ID`, `BQ_DATASET`.