from pathlib import Path
from typing import cast
import duckdb
import pandas as pd
import streamlit as st


def filter_dataframe(df: pd.DataFrame, key: str) -> pd.DataFrame:
    if df.empty:
        return df

    search_text = st.text_input("Search", key=f"search_{key}").strip().lower()
    if not search_text:
        return df

    mask = df.astype(str).apply(lambda col: col.str.lower().str.contains(search_text, na=False))
    return cast(pd.DataFrame, df.loc[mask.any(axis=1)])


@st.cache_data(show_spinner=False)
def load_duckdb_tables(raw_db_path: Path) -> pd.DataFrame:
    if not raw_db_path.exists():
        return pd.DataFrame()
    with duckdb.connect(str(raw_db_path), read_only=True) as con:
        return cast(pd.DataFrame, con.execute("SHOW TABLES").fetchdf())


@st.cache_data(show_spinner=False)
def load_duckdb_preview(raw_db_path: Path, table_name: str, limit: int | None) -> pd.DataFrame:
    if not raw_db_path.exists():
        return pd.DataFrame()
    with duckdb.connect(str(raw_db_path), read_only=True) as con:
        if limit is None:
            return cast(pd.DataFrame, con.execute(f'SELECT * FROM "{table_name}"').fetchdf())
        return cast(pd.DataFrame, con.execute(f'SELECT * FROM "{table_name}" LIMIT {int(limit)}').fetchdf())


@st.cache_data(show_spinner=False)
def get_duckdb_table_row_count(raw_db_path: Path, table_name: str) -> int:
    if not raw_db_path.exists():
        return 0
    with duckdb.connect(str(raw_db_path), read_only=True) as con:
        row = con.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()
    return int(row[0]) if row else 0


def render_duckdb_tab(raw_db_path: Path) -> None:
    st.subheader("DuckDB Explorer & SQL Console")
    st.caption(f"Database: `{raw_db_path}`")

    if not raw_db_path.exists():
        st.warning("⚠️ Chưa tìm thấy file DB. Hãy cào dữ liệu trước.")
        return

    # --- Phần 1: Gõ lệnh SQL trực tiếp (SQL Console) ---
    st.markdown("### 💻 SQL Query Console")
    st.caption("Bạn có thể viết câu lệnh SQL DuckDB tùy ý tại đây để truy vấn trực tiếp:")

    sample_queries = {
        "1. Xem 10 sản phẩm mới nhất": "SELECT thoi_diem, danh_muc, ten_san_pham, gia_hien_tai, luot_mua, diem_danh_gia FROM scraped_raw_items_v2 ORDER BY thoi_diem DESC LIMIT 10",
        "2. Thống kê sản phẩm theo danh mục": "SELECT danh_muc, COUNT(DISTINCT id_product) AS so_san_pham, COUNT(*) AS tong_snapshot, AVG(gia_hien_tai) AS gia_tb FROM scraped_raw_items_v2 GROUP BY danh_muc ORDER BY so_san_pham DESC",
        "3. Top 10 sản phẩm bán chạy nhất": "SELECT ten_san_pham, danh_muc, gia_hien_tai, luot_mua, (gia_hien_tai * luot_mua) AS doanh_thu_uoc_tinh FROM scraped_raw_items_v2 ORDER BY luot_mua DESC NULLS LAST LIMIT 10",
        "4. Tùy chỉnh câu lệnh riêng": ""
    }

    selected_sample = st.selectbox("📌 Chọn câu lệnh SQL mẫu hoặc tự viết:", list(sample_queries.keys()))
    default_sql = sample_queries[selected_sample] if sample_queries[selected_sample] else "SELECT * FROM scraped_raw_items_v2 LIMIT 15"

    user_sql = st.text_area("✍️ Câu lệnh SQL:", value=default_sql, height=120)

    col_btn, _ = st.columns([1, 4])
    with col_btn:
        run_sql = st.button("🚀 Chạy truy vấn SQL", type="primary")

    if run_sql and user_sql.strip():
        try:
            with duckdb.connect(str(raw_db_path), read_only=False) as con:
                query_result = con.execute(user_sql).fetchdf()
                st.success(f"✅ Truy vấn thành công! Trả về **{len(query_result):,}** dòng kết quả:")
                st.dataframe(query_result, width="stretch")

                # Nút tải kết quả CSV
                csv_data = query_result.to_csv(index=False).encode("utf-8")
                st.download_button(
                    label="📥 Tải kết quả về máy (CSV)",
                    data=csv_data,
                    file_name="duckdb_query_result.csv",
                    mime="text/csv"
                )
        except Exception as e:
            st.error(f"❌ Lỗi thực thi SQL: {e}")

    st.divider()

    # --- Phần 2: Xem toàn bộ các bảng trong DB ---
    st.markdown("### 📋 Danh sách bảng trong Database")
    tables_df = load_duckdb_tables(raw_db_path)
    if tables_df.empty:
        st.info("DB chưa có bảng nào.")
        return

    st.dataframe(tables_df, width="stretch")
    table_name = cast(str, st.selectbox("Chọn bảng để xem nhanh:", tables_df["name"].tolist()))
    total_rows = get_duckdb_table_row_count(raw_db_path, table_name)
    st.caption(f"Tổng số dòng trong bảng `{table_name}`: **{total_rows:,}** dòng")

    slider_key = f"duckdb_rows_slider_{table_name}"
    input_key = f"duckdb_rows_input_{table_name}"
    default_rows = min(100, total_rows)

    if slider_key not in st.session_state:
        st.session_state[slider_key] = default_rows
    if input_key not in st.session_state:
        st.session_state[input_key] = default_rows

    st.session_state[slider_key] = min(max(int(st.session_state[slider_key]), 0), total_rows)
    st.session_state[input_key] = min(max(int(st.session_state[input_key]), 0), total_rows)

    def _sync_slider_from_input() -> None:
        value = min(max(int(st.session_state[input_key]), 0), total_rows)
        st.session_state[input_key] = value
        st.session_state[slider_key] = value

    def _sync_input_from_slider() -> None:
        value = min(max(int(st.session_state[slider_key]), 0), total_rows)
        st.session_state[slider_key] = value
        st.session_state[input_key] = value

    col_slider, col_input = st.columns([3, 1])
    with col_slider:
        st.slider(
            "Số dòng hiển thị",
            min_value=0,
            max_value=total_rows,
            step=1,
            key=slider_key,
            on_change=_sync_input_from_slider,
        )
    with col_input:
        st.number_input(
            "Nhập số dòng",
            min_value=0,
            max_value=total_rows,
            step=1,
            key=input_key,
            on_change=_sync_slider_from_input,
        )

    limit = int(st.session_state[slider_key])
    preview_df = load_duckdb_preview(raw_db_path, table_name=table_name, limit=limit)
    preview_df = filter_dataframe(preview_df, f"db_{table_name}")

    column_config = None
    if "product_url" in preview_df.columns:
        preview_df = preview_df.copy()
        preview_df["chi_tiet"] = preview_df["product_url"]
        column_config = {
            "product_url": st.column_config.LinkColumn("Product URL", display_text="Mở link"),
            "chi_tiet": st.column_config.LinkColumn("Chi tiết", display_text="Chi tiết"),
        }

    st.dataframe(preview_df, width="stretch", column_config=column_config)
