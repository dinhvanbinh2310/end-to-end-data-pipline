file_path = '../../data/staging/products.parquet'

if not os.path.exists(file_path):
    print(f"❌ Không tìm thấy file tại: {os.path.abspath(file_path)}")
else:
    df = pd.read_parquet(file_path)

    print('=== TỔNG QUAN ===')
    print(f'Sản phẩm: {len(df):,}')

    print(f'Danh mục: {df["danh_muc"].nunique()} loại')
    print(f'Thương hiệu: {df["thuong_hieu"].nunique()} brand')
    
    gia_min = int(df["gia"].min()) if pd.notna(df["gia"].min()) else 0
    gia_max = int(df["gia"].max()) if pd.notna(df["gia"].max()) else 0
    print(f'Giá: {gia_min:,} - {gia_max:,} VND')
    
    print(f'so_luong_ban null: {df["so_luong_ban"].isna().sum()}')

    print('\n=== 20 TÊN SẢN PHẨM ĐẦU ===')
    for name in df['ten_san_pham'].head(20):
        print(f'  - {name}')

    print('\n=== TOP 10 DANH MỤC ===')
    print(df['danh_muc'].value_counts().head(10).to_string())