import json
from pathlib import Path

import duckdb
import pandas as pd
import streamlit as st

BASE_DIR = Path(__file__).resolve().parent


def find_data_root() -> Path | None:
    candidates = [
        BASE_DIR / "data",
        BASE_DIR / "src" / "data-engine" / "data",
    ]

    # Prefer the directory that actually contains staging/mart datasets.
    best_candidate = None
    best_score = -1
    for candidate in candidates:
        if not candidate.exists():
            continue

        score = 0
        if (candidate / "staging" / "products.csv").exists():
            score += 1
        if (candidate / "staging" / "attributes.csv").exists():
            score += 1
        if (candidate / "mart" / "products_full.csv").exists():
            score += 1

        if score > best_score:
            best_candidate = candidate
            best_score = score

    return best_candidate


DATA_ROOT = find_data_root()


@st.cache_data(show_spinner=False)
def load_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path)


@st.cache_data(show_spinner=False)
def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


@st.cache_data(show_spinner=False)
def load_raw_table(raw_dir: Path) -> pd.DataFrame:
    records = []
    if not raw_dir.exists():
        return pd.DataFrame()

    for path in sorted(raw_dir.glob("*.json")):
        try:
            payload = load_json(path)
        except Exception:
            continue

        item = payload.get("data", {}).get("item", {})
        categories = item.get("categories") or []
        item_rating = item.get("item_rating") or {}

        records.append(
            {
                "file_name": path.name,
                "item_id": item.get("item_id"),
                "shop_id": item.get("shop_id"),
                "category": categories[0].get("display_name") if categories else None,
                "title": item.get("title"),
                "price_min": item.get("price_min"),
                "price_max": item.get("price_max"),
                "currency": item.get("currency"),
                "rating_star": item_rating.get("rating_star"),
                "sold": item.get("historical_sold"),
                "shop_location": item.get("shop_location"),
            }
        )

    df = pd.DataFrame(records)
    if df.empty:
        return df

    for col in ["item_id", "shop_id", "price_min", "price_max", "sold"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["rating_star"] = pd.to_numeric(df["rating_star"], errors="coerce")
    return df


@st.cache_data(show_spinner=False)
def load_duckdb_tables(db_path: Path) -> pd.DataFrame:
    with duckdb.connect(str(db_path), read_only=True) as conn:
        return conn.execute("SHOW TABLES").fetchdf()


@st.cache_data(show_spinner=False)
def load_duckdb_preview(db_path: Path, table_name: str, limit: int) -> pd.DataFrame:
    query = f'SELECT * FROM "{table_name}" LIMIT {int(limit)}'
    with duckdb.connect(str(db_path), read_only=True) as conn:
        return conn.execute(query).fetchdf()


def get_dataset_paths(root: Path) -> dict[str, Path]:
    return {
        "products": root / "staging" / "products.csv",
        "models": root / "staging" / "models.csv",
        "attributes": root / "staging" / "attributes.csv",
        "shops": root / "staging" / "shops.csv",
        "mart": root / "mart" / "products_full.csv",
        "raw_dir": root / "raw",
        "clean_dir": root / "staging" / "clean",
    }


def format_money(value: float | int | None) -> str:
    if pd.isna(value):
        return "N/A"
    return f"{value:,.0f} VND"


def normalize_price_series(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.dropna().empty:
        return numeric
    if numeric.max() >= 1_000_000_000:
        return numeric / 100_000
    return numeric


def render_metrics(dataset_map: dict[str, pd.DataFrame]) -> None:
    left, middle, right = st.columns(3)
    with left:
        st.metric("Số sản phẩm", len(dataset_map.get("products", pd.DataFrame())))
    with middle:
        st.metric("Số shop", len(dataset_map.get("shops", pd.DataFrame())))
    with right:
        st.metric("Số models", len(dataset_map.get("models", pd.DataFrame())))


def render_dataframe_with_search(df: pd.DataFrame, key: str) -> None:
    if df.empty:
        st.info("Không có dữ liệu")
        return

    search_text = st.text_input("Tìm kiếm", key=f"search_{key}").strip().lower()
    filtered = df.copy()

    if search_text:
        mask = filtered.astype(str).apply(lambda col: col.str.lower().str.contains(search_text, na=False))
        filtered = filtered[mask.any(axis=1)]

    page_size = st.selectbox("Số dòng mỗi trang", [20, 50, 100, 200], index=1, key=f"size_{key}")
    st.dataframe(filtered.head(page_size), use_container_width=True)
    st.caption(f"Đang hiển thị {min(len(filtered), page_size)}/{len(filtered)} dòng")


def render_raw_tab(paths: dict[str, Path]) -> None:
    raw_files = sorted(paths["raw_dir"].glob("*.json")) if paths["raw_dir"].exists() else []
    clean_files = sorted(paths["clean_dir"].glob("*.json")) if paths["clean_dir"].exists() else []

    st.subheader("Raw Data")
    if not raw_files and not clean_files:
        st.warning("Chưa tìm thấy file JSON trong raw hoặc clean")
        return

    raw_df = load_raw_table(paths["raw_dir"])
    st.caption("Bảng tổng hợp dữ liệu raw theo từng file JSON")
    render_dataframe_with_search(raw_df, "raw_table")

    st.divider()
    st.caption("Xem JSON chi tiết")

    raw_col, clean_col = st.columns(2)
    with raw_col:
        selected_raw = st.selectbox(
            "Raw file",
            ["(không chọn)"] + [f.name for f in raw_files],
            key="raw_file_picker",
        )
    with clean_col:
        selected_clean = st.selectbox(
            "Clean file",
            ["(không chọn)"] + [f.name for f in clean_files],
            key="clean_file_picker",
        )

    if selected_raw != "(không chọn)":
        content = load_json(paths["raw_dir"] / selected_raw)
        st.json(content, expanded=False)

    if selected_clean != "(không chọn)":
        content = load_json(paths["clean_dir"] / selected_clean)
        st.json(content, expanded=False)


def render_staging_tab(dataset_map: dict[str, pd.DataFrame]) -> None:
    st.subheader("Staging CSV")
    sub_tabs = st.tabs(["Products", "Models", "Attributes", "Shops"])

    with sub_tabs[0]:
        render_dataframe_with_search(dataset_map["products"], "products")
    with sub_tabs[1]:
        render_dataframe_with_search(dataset_map["models"], "models")
    with sub_tabs[2]:
        attr_df = dataset_map["attributes"]
        if attr_df.empty:
            st.info("Không có dữ liệu")
        else:
            st.caption("Tìm kiếm theo thuộc tính")
            left, middle, right = st.columns([2, 3, 3])

            attr_names = sorted(
                [
                    x
                    for x in attr_df["attr_name"].dropna().astype(str).unique().tolist()
                    if x.strip()
                ]
            )
            with left:
                selected_attr = st.selectbox("Thuộc tính", ["(tất cả)"] + attr_names, key="stg_attr_name")

            filtered_attr = attr_df.copy()
            if selected_attr != "(tất cả)":
                filtered_attr = filtered_attr[filtered_attr["attr_name"].astype(str) == selected_attr]

            attr_values = sorted(
                [
                    x
                    for x in filtered_attr["attr_value"].dropna().astype(str).unique().tolist()
                    if x.strip()
                ]
            )
            with middle:
                selected_values = st.multiselect("Giá trị thuộc tính", attr_values, key="stg_attr_values")
            if selected_values:
                filtered_attr = filtered_attr[filtered_attr["attr_value"].astype(str).isin(selected_values)]

            with right:
                attr_keyword = st.text_input("Keyword trong giá trị", key="stg_attr_kw").strip().lower()
            if attr_keyword:
                filtered_attr = filtered_attr[
                    filtered_attr["attr_value"].astype(str).str.lower().str.contains(attr_keyword, na=False)
                ]

            render_dataframe_with_search(filtered_attr, "attributes")
    with sub_tabs[3]:
        render_dataframe_with_search(dataset_map["shops"], "shops")


def render_mart_tab(mart_df: pd.DataFrame, attributes_df: pd.DataFrame) -> None:
    st.subheader("Mart - products_full")
    if mart_df.empty:
        st.warning("Không có dữ liệu products_full.csv")
        return

    filtered = mart_df.copy()

    if "category_name" in filtered.columns:
        categories = sorted([x for x in filtered["category_name"].dropna().unique().tolist()])
        selected_categories = st.multiselect("Lọc theo category", categories)
        if selected_categories:
            filtered = filtered[filtered["category_name"].isin(selected_categories)]

    if "shop_name" in filtered.columns:
        shops = sorted([x for x in filtered["shop_name"].dropna().unique().tolist()])
        selected_shops = st.multiselect("Lọc theo shop", shops)
        if selected_shops:
            filtered = filtered[filtered["shop_name"].isin(selected_shops)]

    if not attributes_df.empty and "item_id" in filtered.columns:
        st.caption("Tìm kiếm theo thuộc tính")
        attr_left, attr_mid, attr_right = st.columns([2, 2, 3])

        attr_names = sorted([x for x in attributes_df["attr_name"].dropna().astype(str).unique().tolist() if x.strip()])
        with attr_left:
            selected_attr = st.selectbox("Thuộc tính", ["(không lọc)"] + attr_names)

        if selected_attr != "(không lọc)":
            attr_values = sorted(
                [
                    x
                    for x in attributes_df.loc[
                        attributes_df["attr_name"].astype(str) == selected_attr,
                        "attr_value",
                    ]
                    .dropna()
                    .astype(str)
                    .unique()
                    .tolist()
                    if x.strip()
                ]
            )
            with attr_mid:
                selected_attr_values = st.multiselect("Giá trị", attr_values, key="mart_attr_values")
            with attr_right:
                attr_keyword = st.text_input("Tìm thêm trong giá trị thuộc tính", value="", key="mart_attr_kw").strip().lower()

            attr_subset = attributes_df[attributes_df["attr_name"].astype(str) == selected_attr].copy()
            if selected_attr_values:
                attr_subset = attr_subset[attr_subset["attr_value"].astype(str).isin(selected_attr_values)]
            if attr_keyword:
                attr_subset = attr_subset[
                    attr_subset["attr_value"].astype(str).str.lower().str.contains(attr_keyword, na=False)
                ]

            attr_item_ids = pd.to_numeric(attr_subset["item_id"], errors="coerce").dropna().astype("Int64").tolist()
            filtered = filtered[pd.to_numeric(filtered["item_id"], errors="coerce").isin(attr_item_ids)]

    price_col = None
    for candidate in ["cheapest_price", "price_min", "price_max"]:
        if candidate in filtered.columns:
            price_col = candidate
            break

    m1, m2, m3 = st.columns(3)
    m1.metric("Số dòng", len(filtered))
    if price_col:
        display_price = normalize_price_series(filtered[price_col])
        m2.metric("Giá trung bình", format_money(display_price.mean()))
        m3.metric("Giá cao nhất", format_money(display_price.max()))

    if "category_name" in filtered.columns:
        top_category = (
            filtered["category_name"]
            .value_counts()
            .head(10)
            .rename_axis("category")
            .reset_index(name="count")
        )
        st.caption("Top category theo số lượng sản phẩm")
        st.bar_chart(top_category.set_index("category")["count"])

    render_dataframe_with_search(filtered, "mart")


def render_duckdb_tab() -> None:
    st.subheader("DuckDB")
    db_path = BASE_DIR / "data" / "tiki_scraped_data.duckdb"

    if not db_path.exists():
        st.info("Không tìm thấy data/tiki_scraped_data.duckdb")
        return

    st.caption(f"Database: {db_path}")
    tables_df = load_duckdb_tables(db_path)
    if tables_df.empty:
        st.info("Database chưa có bảng")
        return

    st.dataframe(tables_df, width="stretch")
    table_name = st.selectbox("Chọn bảng để xem", tables_df["name"].tolist())
    limit = st.slider("Số dòng preview", min_value=10, max_value=1000, value=100, step=10)

    preview_df = load_duckdb_preview(db_path, table_name, limit)
    st.caption("Tìm kiếm trong bảng DuckDB")
    render_dataframe_with_search(preview_df, f"duckdb_{table_name}")


def main() -> None:
    st.set_page_config(page_title="Scraped Data Viewer", layout="wide")
    st.title("Scraped Data Viewer")
    st.caption("Frontend Streamlit để xem raw, staging, mart và DuckDB")

    if DATA_ROOT is None:
        st.error("Không tìm thấy thư mục dữ liệu. Cần có data/ hoặc src/data-engine/data/")
        st.stop()

    paths = get_dataset_paths(DATA_ROOT)

    dataset_map: dict[str, pd.DataFrame] = {}
    for name in ["products", "models", "attributes", "shops", "mart"]:
        csv_path = paths[name]
        if csv_path.exists():
            dataset_map[name] = load_csv(csv_path)
        else:
            dataset_map[name] = pd.DataFrame()

    with st.sidebar:
        st.header("Nguồn dữ liệu")
        st.write(f"Data root: {DATA_ROOT}")
        for name in ["products", "models", "attributes", "shops", "mart"]:
            status = "OK" if not dataset_map[name].empty else "Thiếu hoặc rỗng"
            st.write(f"- {name}: {status}")

    render_metrics(dataset_map)

    tabs = st.tabs(["Raw", "Staging", "Mart", "DuckDB"])
    with tabs[0]:
        render_raw_tab(paths)
    with tabs[1]:
        render_staging_tab(dataset_map)
    with tabs[2]:
        render_mart_tab(dataset_map["mart"], dataset_map["attributes"])
    with tabs[3]:
        render_duckdb_tab()


if __name__ == "__main__":
    main()
