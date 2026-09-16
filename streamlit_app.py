# pyright: reportCallIssue=false
# pyright: reportArgumentType=false, reportCallIssue=false
# pyright: reportCallIssue=false, reportArgumentType=false
# pyright: reportCallIssue=false, reportArgumentType=false
# pyright: reportCallIssue=false, reportArgumentType=false
import sys
from typing import Any, cast
from pathlib import Path
from datetime import datetime, timedelta

import duckdb
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import altair as alt

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
RAW_DB_PATH = DATA_DIR / "tiki_scraped_data_raw.duckdb"

SCRAPER_DIR = BASE_DIR / "src" / "scraper-services"
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(SCRAPER_DIR))

try:
    from tiki_scraper import crawl_new_products, sync_prices_from_existing
except Exception:
    crawl_new_products = None
    sync_prices_from_existing = None

from src.duckdb_tab import render_duckdb_tab


def filter_dataframe(df: pd.DataFrame, key: str) -> pd.DataFrame:
    if df.empty:
        return df

    search_text = st.text_input("Search", key=f"search_{key}").strip().lower()
    if not search_text:
        return df

    mask = df.astype(str).apply(lambda col: col.str.lower().str.contains(search_text, na=False))
    return cast(pd.DataFrame, df.loc[mask.any(axis=1)])


@st.cache_data(show_spinner=False)
def load_raw_snapshots(limit: int = 2000) -> pd.DataFrame:
    if not RAW_DB_PATH.exists():
        return pd.DataFrame()

    with duckdb.connect(str(RAW_DB_PATH), read_only=True) as con:
        row = con.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'scraped_raw_items_v2'"
        ).fetchone()
        if not row or not row[0]:
            return pd.DataFrame()

        cols = [row[0] for row in con.execute("DESCRIBE scraped_raw_items_v2").fetchall()]
        wanted = [
            "thoi_diem",
            "kieu_cao",
            "danh_muc",
            "tu_khoa",
            "id_product",
            "ten_san_pham",
            "gia_hien_tai",
            "gia_goc",
            "diem_danh_gia",
            "luot_mua",
            "product_url",
        ]
        selected = [c for c in wanted if c in cols]
        if not selected:
            return pd.DataFrame()

        query = (
            f"SELECT {', '.join(selected)} FROM scraped_raw_items_v2 "
            "ORDER BY TRY_CAST(thoi_diem AS TIMESTAMP) DESC NULLS LAST "
            f"LIMIT {int(limit)}"
        )
        df = con.execute(query).fetchdf()

    for c in wanted:
        if c not in df.columns:
            df[c] = None
    return cast(pd.DataFrame, df[wanted])




@st.cache_data(show_spinner=False)
def load_dashboard_snapshots(max_rows: int = 200000) -> pd.DataFrame:
    if not RAW_DB_PATH.exists():
        return pd.DataFrame()

    with duckdb.connect(str(RAW_DB_PATH), read_only=True) as con:
        row = con.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'scraped_raw_items_v2'"
        ).fetchone()
        if not row or not row[0]:
            return pd.DataFrame()

        cols = [r[0] for r in con.execute("DESCRIBE scraped_raw_items_v2").fetchall()]
        wanted = [
            "thoi_diem",
            "id_product",
            "ten_san_pham",
            "danh_muc",
            "tu_khoa",
            "gia_hien_tai",
            "diem_danh_gia",
            "luot_mua",
            "kieu_cao",
            "product_url",
        ]
        selected = [c for c in wanted if c in cols]
        if not selected:
            return pd.DataFrame()

        query = (
            "SELECT * FROM ("
            f"SELECT {', '.join(selected)} FROM scraped_raw_items_v2 "
            "ORDER BY TRY_CAST(thoi_diem AS TIMESTAMP) DESC NULLS LAST "
            f"LIMIT {int(max_rows)}"
            ") t "
            "ORDER BY TRY_CAST(thoi_diem AS TIMESTAMP) ASC NULLS LAST"
        )
        df = con.execute(query).fetchdf()

    if df.empty:
        return df

    if "thoi_diem" in df.columns:
        df["thoi_diem"] = pd.to_datetime(df["thoi_diem"], errors="coerce")
    if "gia_hien_tai" in df.columns:
        df["gia_hien_tai"] = pd.to_numeric(df["gia_hien_tai"], errors="coerce")
    if "diem_danh_gia" in df.columns:
        df["diem_danh_gia"] = pd.to_numeric(df["diem_danh_gia"], errors="coerce")
    if "luot_mua" in df.columns:
        df["luot_mua"] = pd.to_numeric(df["luot_mua"], errors="coerce")
    if "id_product" in df.columns:
        s = cast(pd.Series, pd.to_numeric(df["id_product"], errors="coerce"))
        df["id_product"] = s.astype("Int64")

    return cast(pd.DataFrame, df.dropna(subset=["thoi_diem", "id_product"]))


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        v = float(value)  # type: ignore[arg-type]
        return int(v) if not pd.isna(v) else default
    except (ValueError, TypeError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        v = float(value)  # type: ignore[arg-type]
        return v if not pd.isna(v) else default
    except (ValueError, TypeError):
        return default


MANUAL_VOLATILE_PAIRS: list[tuple[str, str]] = [
    ("dien_thoai", "iphone"),
    ("laptop", "macbook"),
    ("giay", "giay sneaker"),
    ("ao", "ao thun nam"),
    ("quan", "quan jean nam"),
    ("my_pham", "serum duong da"),
    ("dong_ho", "dong ho nam"),
    ("tui_xach", "tui xach nu"),
    ("phu_kien", "tai nghe bluetooth"),
    ("do_gia_dung", "noi chien khong dau"),
]

MANUAL_DEFAULT_KEYWORDS: dict[str, str] = {danh_muc: tu_khoa for danh_muc, tu_khoa in MANUAL_VOLATILE_PAIRS}
MANUAL_VOLATILE_CATEGORIES: list[str] = [danh_muc for danh_muc, _ in MANUAL_VOLATILE_PAIRS]
DASHBOARD_TARGET_CATEGORIES: list[str] = MANUAL_VOLATILE_CATEGORIES.copy()


def render_crawl_tab() -> None:
    st.subheader("Cào Dữ Liệu Từ Giao Diện")

    if crawl_new_products is None or sync_prices_from_existing is None:
        st.error("Không import được module tiki_scraper. Kiểm tra src/scraper-services/tiki_scraper.py")
        return

    left, right = st.columns(2)

    if "manual_categories_multi" not in st.session_state:
        st.session_state["manual_categories_multi"] = MANUAL_VOLATILE_CATEGORIES.copy()

    with left:
        st.markdown("### Cào mới theo từ khóa")
        selected_manual_categories = cast(
            list[str],
            st.multiselect(
                "Danh mục (chọn nhiều để cào 1 lần)",
                MANUAL_VOLATILE_CATEGORIES,
                default=st.session_state["manual_categories_multi"],
                key="manual_categories_multi",
            ),
        )

        if selected_manual_categories:
            preview_pairs = [f"{cat} | {MANUAL_DEFAULT_KEYWORDS.get(cat, '')}" for cat in selected_manual_categories]
            st.caption("Sẽ cào các cặp: " + "; ".join(preview_pairs))

        with st.form("new_crawl_form"):
            st.caption("Từ khóa sẽ dùng theo bộ gợi ý biến động cao tương ứng từng danh mục.")
            quantity = st.selectbox("Số lượng sản phẩm mỗi danh mục", [1, 3, 5, 10], index=0)
            submit_new = st.form_submit_button("Cào mới")

        if submit_new:
            if not selected_manual_categories:
                st.warning("Chọn ít nhất 1 danh mục trước khi cào.")
            else:
                run_snapshot_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                total_inserted = 0
                total_requested = 0
                run_rows: list[dict[str, object]] = []
                with st.spinner("Đang cào dữ liệu mới..."):
                    for category in selected_manual_categories:
                        keyword = MANUAL_DEFAULT_KEYWORDS.get(category, "").strip()
                        if not keyword:
                            continue

                        result = crawl_new_products(
                            keyword=keyword,
                            quantity=int(quantity),
                            output_dir=str(DATA_DIR),
                            danh_muc=category,
                            snapshot_time=run_snapshot_time,
                        )
                        inserted = int(result.get("inserted", 0))
                        requested = int(result.get("requested", quantity))
                        total_inserted += inserted
                        total_requested += requested
                        run_rows.append(
                            {
                                "danh_muc": category,
                                "tu_khoa": keyword,
                                "inserted": inserted,
                                "requested": requested,
                            }
                        )

                st.success(
                    f"Đã thêm {total_inserted}/{total_requested} bản ghi mới vào DB. Mốc thời gian batch: {run_snapshot_time}."
                )
                if run_rows:
                    st.dataframe(pd.DataFrame(run_rows), width="stretch")
                st.cache_data.clear()

    with right:
        with st.form("sync_old_form"):
            st.markdown("### Sync giá từ sản phẩm cũ")
            max_items = st.selectbox("Số sản phẩm cần sync", [10, 20, 30, 50, 100], index=2)
            delay_seconds = st.slider("Delay mỗi request (giây)", 0.0, 1.5, 0.3, 0.1)
            submit_sync = st.form_submit_button("Sync giá")

        if submit_sync:
            sync_snapshot_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with st.spinner("Đang sync giá sản phẩm cũ..."):
                result = sync_prices_from_existing(
                    output_dir=str(DATA_DIR),
                    max_items=int(max_items),
                    delay_seconds=float(delay_seconds),
                    snapshot_time=sync_snapshot_time,
                )
            if result["success"]:
                st.success(
                    f"Sync thành công. Đã tạo bản ghi mới trong {result['db_path']}. Mốc thời gian batch: {sync_snapshot_time}."
                )
            else:
                st.warning("Không có bản ghi mới được tạo trong lần sync này.")
            st.cache_data.clear()

    st.markdown("---")
    st.markdown("### Tự động cào theo lịch")

    auto_enabled = st.toggle("Bật tự động cào", key="auto_crawl_enabled")
    auto_quantity = st.selectbox("Số lượng mỗi từ khóa", [1, 3, 5, 10], index=0, key="auto_crawl_quantity")
    auto_crawl_interval_min = st.selectbox(
        "Mốc tự động cào",
        [5, 10, 20, 30, 60],
        index=0,
        format_func=lambda x: "1 giờ" if x == 60 else f"{x} phút",
        key="auto_crawl_interval_min",
    )
    auto_interval_sec = st.slider(
        "Chu kỳ kiểm tra (giây)",
        min_value=5,
        max_value=60,
        value=10,
        step=5,
        key="auto_crawl_check_interval",
        help="Trang sẽ tự refresh theo chu kỳ này để bắt đúng mốc phút đã chọn.",
    )
    if "auto_crawl_pairs" not in st.session_state:
        st.session_state["auto_crawl_pairs"] = [
            {"danh_muc": "dien_thoai", "tu_khoa": "iphone"},
            {"danh_muc": "laptop", "tu_khoa": "macbook"},
        ]

    st.markdown("#### Quản lý cặp Danh mục - Từ khóa")
    add_col1, add_col2, add_col3 = st.columns([2, 2, 1])
    with add_col1:
        new_danh_muc = st.text_input("Danh mục mới", key="auto_new_danh_muc")
    with add_col2:
        new_tu_khoa = st.text_input("Từ khóa mới", key="auto_new_tu_khoa")
    with add_col3:
        st.write("")
        st.write("")
        add_pair = st.button("Thêm cặp", use_container_width=True)

    if add_pair:
        danh_muc_val = new_danh_muc.strip()
        tu_khoa_val = new_tu_khoa.strip()
        if not danh_muc_val or not tu_khoa_val:
            st.warning("Cần nhập đủ Danh mục và Từ khóa để thêm cặp.")
        else:
            pair = {"danh_muc": danh_muc_val, "tu_khoa": tu_khoa_val}
            if pair in st.session_state["auto_crawl_pairs"]:
                st.info("Cặp này đã tồn tại trong danh sách.")
            else:
                st.session_state["auto_crawl_pairs"].append(pair)
                st.success(f"Đã thêm cặp: {danh_muc_val} | {tu_khoa_val}")

    pairs_df = pd.DataFrame(st.session_state["auto_crawl_pairs"])
    if not pairs_df.empty:
        st.caption("Danh sách cặp đang bật (bấm Hủy ngay trên từng dòng):")
        for idx, row in enumerate(st.session_state["auto_crawl_pairs"]):
            row_col1, row_col2, row_col3 = st.columns([2, 2, 1])
            with row_col1:
                st.text_input(
                    f"danh_muc_{idx}",
                    value=row["danh_muc"],
                    disabled=True,
                    label_visibility="collapsed",
                )
            with row_col2:
                st.text_input(
                    f"tu_khoa_{idx}",
                    value=row["tu_khoa"],
                    disabled=True,
                    label_visibility="collapsed",
                )
            with row_col3:
                if st.button("Hủy", key=f"remove_pair_{idx}", use_container_width=True):
                    removed = st.session_state["auto_crawl_pairs"].pop(idx)
                    st.success(f"Đã hủy cặp: {removed['danh_muc']} | {removed['tu_khoa']}")
                    st.rerun()

        if st.button("Hủy tất cả cặp", key="remove_all_pairs"):
            st.session_state["auto_crawl_pairs"] = []
            st.success("Đã hủy tất cả cặp tự động cào.")
            st.rerun()
    else:
        st.info("Chưa có cặp nào trong danh sách tự động cào.")

    parsed_targets: list[tuple[str, str]] = [
        (p["danh_muc"], p["tu_khoa"]) for p in st.session_state["auto_crawl_pairs"]
    ]
    st.caption(f"Tổng cặp đang bật cho tự động cào: {len(parsed_targets)}")

    now = datetime.now()
    if auto_crawl_interval_min == 60:
        next_run = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    else:
        next_step = (now.minute // int(auto_crawl_interval_min) + 1) * int(auto_crawl_interval_min)
        next_hour = now
        if next_step >= 60:
            next_step = next_step % 60
            next_hour = now + timedelta(hours=1)
        next_run = next_hour.replace(minute=next_step, second=0, microsecond=0)
    remaining = next_run - now
    remaining_minutes = int(remaining.total_seconds() // 60)
    remaining_seconds = int(remaining.total_seconds() % 60)
    interval_label = "1 giờ" if auto_crawl_interval_min == 60 else f"{auto_crawl_interval_min} phút"
    next_run_ts_ms = int(next_run.timestamp() * 1000)
    countdown_id = f"auto-crawl-countdown-{next_run.strftime('%Y%m%d%H%M%S')}"
    components.html(
        f"""
        <div id=\"{countdown_id}\" style=\"font-size: 0.95rem; color: #F5F7FA;\">
            Mốc cào hiện tại: mỗi {interval_label}. Lần cào tiếp theo dự kiến lúc {next_run.strftime('%H:%M:%S')} (còn {remaining_minutes:02d}:{remaining_seconds:02d}).
        </div>
        <script>
            (function() {{
                let target = {next_run_ts_ms};
                const intervalMs = {int(auto_crawl_interval_min)} * 60 * 1000;
                const el = document.getElementById("{countdown_id}");
                if (!el) return;

                function pad(n) {{ return String(n).padStart(2, "0"); }}

                function formatTime(ts) {{
                    const d = new Date(ts);
                    return pad(d.getHours()) + ":" + pad(d.getMinutes()) + ":" + pad(d.getSeconds());
                }}

                function tick() {{
                    const now = Date.now();
                    while (target <= now) {{
                        target += intervalMs;
                    }}

                    const diff = Math.floor((target - now) / 1000);

                    const minutes = Math.floor(diff / 60);
                    const seconds = diff % 60;
                    el.textContent = "Mốc cào hiện tại: mỗi {interval_label}. Lần cào tiếp theo dự kiến lúc " + formatTime(target) + " (còn " + pad(minutes) + ":" + pad(seconds) + ").";
                }}

                tick();
                setInterval(tick, 1000);
            }})();
        </script>
        """,
        height=32,
    )

    if auto_enabled:
        autorefresh_fn = getattr(st, "autorefresh", None)
        if callable(autorefresh_fn):
            autorefresh_fn(interval=auto_interval_sec * 1000, key="auto_crawl_autorefresh")
        else:
            components.html(
                f"""
                <script>
                setTimeout(function() {{
                    window.parent.location.reload();
                }}, {auto_interval_sec * 1000});
                </script>
                """,
                height=0,
            )

        if auto_crawl_interval_min == 60:
            should_run_now = now.minute == 0
            run_slot_key = now.strftime("%Y-%m-%d %H:00")
        else:
            should_run_now = (now.minute % int(auto_crawl_interval_min) == 0)
            run_slot_key = now.strftime("%Y-%m-%d %H:%M")

        last_run_slot = st.session_state.get("auto_crawl_last_slot")

        if should_run_now and run_slot_key != last_run_slot:
            if not parsed_targets:
                st.warning("Chưa có danh mục hoặc từ khóa hợp lệ để tự động cào.")
            else:
                total_inserted = 0
                total_requested = 0
                auto_snapshot_time = now.strftime("%Y-%m-%d %H:%M:%S")
                with st.spinner("Đang tự động cào dữ liệu đầu giờ..."):
                    for danh_muc, tu_khoa in parsed_targets:
                        result = crawl_new_products(
                            keyword=tu_khoa,
                            quantity=int(auto_quantity),
                            output_dir=str(DATA_DIR),
                            danh_muc=danh_muc,
                            snapshot_time=auto_snapshot_time,
                        )
                        total_inserted += int(result.get("inserted", 0))
                        total_requested += int(result.get("requested", 0))

                st.session_state["auto_crawl_last_slot"] = run_slot_key
                st.success(
                    f"Auto crawl {now.strftime('%H:%M')} hoàn tất: {total_inserted}/{total_requested} bản ghi mới. Mốc batch: {auto_snapshot_time}."
                )
                st.cache_data.clear()
        else:
            st.info(
                f"Auto crawl đang bật. Lần chạy gần nhất: {st.session_state.get('auto_crawl_last_slot', 'chưa có')}."
            )


def render_snapshot_tab() -> None:
    st.subheader("Bản Ghi Snapshots")

    top_left, top_mid = st.columns(2)
    with top_left:
        limit = st.selectbox("Số dòng tải", [100, 300, 500, 1000, 2000], index=1)
    with top_mid:
        mode_filter = st.multiselect("Lọc theo kiểu cào", ["new", "sync"])

    df = load_raw_snapshots(limit=limit)
    if df.empty:
        st.info("Chưa có dữ liệu trong bảng scraped_raw_items_v2")
        return

    if mode_filter and "kieu_cao" in df.columns:
        df = cast(pd.DataFrame, df[df["kieu_cao"].isin(mode_filter)])

    df = filter_dataframe(cast(pd.DataFrame, df), "snapshots")
    page_size = st.selectbox("Số dòng hiển thị", [20, 50, 100, 200], index=1)

    st.dataframe(
        df.head(page_size),
        width="stretch",
        column_config={
            "product_url": st.column_config.LinkColumn("Chi tiết sản phẩm", display_text="Mở"),
            "gia_hien_tai": st.column_config.NumberColumn("Giá hiện tại", format="%d"),
            "gia_goc": st.column_config.NumberColumn("Giá gốc", format="%d"),
            "luot_mua": st.column_config.NumberColumn("Lượt mua", format="%d"),
        },
    )
    st.caption(f"Đang hiển thị {min(len(df), page_size)}/{len(df)} dòng")


def render_dashboard_tab() -> None:
    st.subheader("Dashboard Biến Động Theo Danh Mục")
    st.caption("Thống kê theo 10 danh mục mục tiêu: số sản phẩm, giá trung bình, rating trung bình, lượt mua")

    df = load_dashboard_snapshots()
    if df.empty:
        st.info("Chưa có dữ liệu để tạo dashboard.")
        return

    col1, col2, col3 = st.columns(3)
    with col1:
        danh_muc_options = sorted([v for v in df["danh_muc"].dropna().astype(str).unique().tolist() if v])
        danh_muc_filter = st.multiselect("Danh mục", danh_muc_options)
    with col2:
        tu_khoa_options = sorted([v for v in df["tu_khoa"].dropna().astype(str).unique().tolist() if v])
        tu_khoa_filter = st.multiselect("Từ khóa", tu_khoa_options)
    with col3:
        mode_filter = st.multiselect("Kiểu cào", ["new", "sync"])

    filtered: pd.DataFrame = cast(pd.DataFrame, df.copy())
    if danh_muc_filter:
        filtered = cast(pd.DataFrame, filtered[cast(pd.Series, filtered["danh_muc"]).astype(str).isin(danh_muc_filter)])
    if tu_khoa_filter:
        filtered = cast(pd.DataFrame, filtered[cast(pd.Series, filtered["tu_khoa"]).astype(str).isin(tu_khoa_filter)])
    if mode_filter and "kieu_cao" in filtered.columns:
        filtered = cast(pd.DataFrame, filtered[cast(pd.Series, filtered["kieu_cao"]).astype(str).isin(mode_filter)])

    if filtered.empty:
        st.warning("Không có dữ liệu sau khi lọc.")
        return

    filtered = cast(pd.DataFrame, filtered[cast(pd.Series, filtered["danh_muc"]).fillna("").astype(str).str.strip() != ""])
    filtered = cast(pd.DataFrame, filtered[cast(pd.Series, filtered["danh_muc"]).astype(str).isin(DASHBOARD_TARGET_CATEGORIES)])
    if filtered.empty:
        st.warning("Không có dữ liệu danh mục sau khi lọc.")
        return

    # Mỗi sản phẩm lấy snapshot mới nhất để thống kê current-state theo danh mục.
    latest_per_product = cast(
        pd.DataFrame,
        filtered.sort_values("thoi_diem")
        .drop_duplicates(subset=["id_product"], keep="last")
        .copy(),
    )
    latest_per_product["doanh_thu_uoc_tinh"] = (
        latest_per_product["gia_hien_tai"].fillna(0) * latest_per_product["luot_mua"].fillna(0)
    )

    total_products = int(latest_per_product["id_product"].nunique())
    total_categories = int(latest_per_product["danh_muc"].nunique())
    avg_price = _safe_float(latest_per_product["gia_hien_tai"].mean(), 0.0)
    avg_rating = _safe_float(latest_per_product["diem_danh_gia"].mean(), 0.0)

    # 1. Hiển thị KPI Metrics ngay trên đầu
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Tổng sản phẩm", f"{total_products:,}")
    m2.metric("Tổng danh mục", f"{total_categories:,}")
    m3.metric("Giá trung bình", f"{int(avg_price):,}")
    m4.metric("Rating trung bình", f"{avg_rating:.2f}")

    category_summary: pd.DataFrame = cast(
        pd.DataFrame,
        latest_per_product.groupby("danh_muc", as_index=False)
        .agg(
            so_san_pham=("id_product", "nunique"),
            tong_gia=("doanh_thu_uoc_tinh", "sum"),
            gia_trung_binh=("gia_hien_tai", "mean"),
            rating_trung_binh=("diem_danh_gia", "mean"),
            luot_mua_trung_binh=("luot_mua", "mean"),
            luot_mua_tong=("luot_mua", "sum"),
        )
        .sort_values("so_san_pham", ascending=False)
    )

    # 2. Biểu đồ chính lên ngay sau Metrics
    st.markdown("### 📊 Biểu đồ phân tích chính")
    metric_map = {
        "Giá": {
            "summary_col": "tong_gia",
            "summary_label": "Doanh thu ước tính",
        },
        "Điểm đánh giá": {
            "summary_col": "rating_trung_binh",
            "summary_label": "Điểm đánh giá trung bình",
        },
        "Lượt mua": {
            "summary_col": "luot_mua_tong",
            "summary_label": "Tổng bán",
        },
    }

    selected_bar_pie_metric = cast(
        str,
        st.selectbox(
            "Tiêu chí cho biểu đồ cột và tròn",
            ["Giá", "Điểm đánh giá", "Lượt mua"],
            index=2,
        ),
    )
    bar_pie_col = cast(str, metric_map[selected_bar_pie_metric]["summary_col"])
    bar_pie_label = cast(str, metric_map[selected_bar_pie_metric]["summary_label"])
    chart_col1, chart_col2 = st.columns(2)
    with chart_col1:
        st.caption(f"Biểu đồ cột ngang: Top danh mục theo {bar_pie_label.lower()}")
        bar_data = category_summary.sort_values(bar_pie_col, ascending=False).head(10).copy()
        bar_data["danh_muc"] = bar_data["danh_muc"].astype(str)
        horizontal_bar = (
            alt.Chart(bar_data)
            .mark_bar()
            .encode(
                x=alt.X(f"{bar_pie_col}:Q", title=bar_pie_label),
                y=alt.Y("danh_muc:N", sort="-x", title="Danh mục"),
                tooltip=["danh_muc", bar_pie_col, "luot_mua_tong", "tong_gia", "so_san_pham", "gia_trung_binh", "rating_trung_binh"],
            )
            .properties(height=320)
        )
        st.altair_chart(horizontal_bar, width="stretch")

    with chart_col2:
        st.caption(f"Biểu đồ tròn: Tỷ trọng danh mục theo {bar_pie_label.lower()}")
        pie_data = category_summary.copy()
        pie_data["danh_muc"] = pie_data["danh_muc"].astype(str)
        pie_chart = (
            alt.Chart(pie_data)
            .mark_arc(innerRadius=55)
            .encode(
                theta=alt.Theta(f"{bar_pie_col}:Q", title=bar_pie_label),
                color=alt.Color("danh_muc:N", title="Danh mục"),
                tooltip=["danh_muc", bar_pie_col, "luot_mua_tong", "tong_gia", "so_san_pham"],
            )
            .properties(height=320)
        )
        st.altair_chart(pie_chart, width="stretch")

    st.markdown("### Biểu đồ đường: 3 tiêu chí theo thời gian")
    trend_categories = st.multiselect(
        "Danh mục hiển thị trên biểu đồ",
        DASHBOARD_TARGET_CATEGORIES,
        default=[cat for cat in DASHBOARD_TARGET_CATEGORIES if cat in set(category_summary["danh_muc"].astype(str).tolist())],
    )

    trend_df = filtered.copy()
    trend_df["moc_thoi_gian"] = trend_df["thoi_diem"].dt.floor("min")
    trend_df["doanh_thu_uoc_tinh"] = trend_df["gia_hien_tai"].fillna(0) * trend_df["luot_mua"].fillna(0)
    if trend_categories:
        trend_df = trend_df[trend_df["danh_muc"].astype(str).isin(trend_categories)]

    if not trend_df.empty:
        minute_totals = (
            trend_df.groupby("moc_thoi_gian", as_index=False)
            .agg(
                tong_gia=("doanh_thu_uoc_tinh", "sum"),
                rating_tb=("diem_danh_gia", "mean"),
                tong_ban=("luot_mua", "sum"),
            )
            .sort_values("moc_thoi_gian")
        )

        line_base = alt.Chart(minute_totals).encode(
            x=alt.X(
                "moc_thoi_gian:T",
                title="Thời điểm (ngày/tháng/năm giờ:phút)",
                axis=alt.Axis(format="%d/%m/%Y %H:%M", labelAngle=-28),
            )
        )

        line_tong_gia = line_base.mark_line(color="#B22222", strokeWidth=2.5).encode(
            y=alt.Y(
                "tong_gia:Q",
                axis=alt.Axis(title="Doanh thu ước tính", titleColor="#B22222", labelColor="#B22222"),
            ),
            tooltip=[
                alt.Tooltip("moc_thoi_gian:T", title="Thời điểm", format="%d/%m/%Y %H:%M"),
                alt.Tooltip("tong_gia:Q", title="Doanh thu ước tính", format=",.0f"),
                alt.Tooltip("tong_ban:Q", title="Tổng bán", format=",.0f"),
                alt.Tooltip("rating_tb:Q", title="Điểm đánh giá TB", format=".2f"),
            ],
        )
        point_tong_gia = line_base.mark_circle(color="#B22222", size=80, opacity=0.9).encode(
            y=alt.Y("tong_gia:Q", axis=alt.Axis(title=None, labels=False, ticks=False, grid=False)),
            tooltip=[
                alt.Tooltip("moc_thoi_gian:T", title="Thời điểm", format="%d/%m/%Y %H:%M"),
                alt.Tooltip("tong_gia:Q", title="Doanh thu ước tính", format=",.0f"),
            ],
        )

        line_rating = line_base.mark_line(color="#F39C12", strokeDash=[6, 4], strokeWidth=2).encode(
            y=alt.Y("rating_tb:Q", axis=alt.Axis(title=None, labels=False, ticks=False, grid=False))
        )
        point_rating = line_base.mark_circle(color="#F39C12", size=70, opacity=0.9).encode(
            y=alt.Y("rating_tb:Q", axis=alt.Axis(title=None, labels=False, ticks=False, grid=False)),
            tooltip=[
                alt.Tooltip("moc_thoi_gian:T", title="Thời điểm", format="%d/%m/%Y %H:%M"),
                alt.Tooltip("rating_tb:Q", title="Điểm đánh giá TB", format=".2f"),
            ],
        )

        line_tong_ban = line_base.mark_line(color="#2E8B57", strokeWidth=2.5).encode(
            y=alt.Y(
                "tong_ban:Q",
                axis=alt.Axis(
                    title="Tổng bán",
                    titleColor="#2E8B57",
                    labelColor="#2E8B57",
                    orient="right",
                ),
            )
        )
        point_tong_ban = line_base.mark_circle(color="#2E8B57", size=80, opacity=0.9).encode(
            y=alt.Y("tong_ban:Q", axis=alt.Axis(title=None, labels=False, ticks=False, grid=False)),
            tooltip=[
                alt.Tooltip("moc_thoi_gian:T", title="Thời điểm", format="%d/%m/%Y %H:%M"),
                alt.Tooltip("tong_ban:Q", title="Tổng bán", format=",.0f"),
            ],
        )

        zoom_x = alt.selection_interval(bind="scales", encodings=["x"])

        line_chart = (
            alt.layer(
                line_tong_gia,
                point_tong_gia,
                line_rating,
                point_rating,
                line_tong_ban,
                point_tong_ban,
            )
            .resolve_scale(y="independent")
            .add_params(zoom_x)
            .properties(height=360)
        )
        st.altair_chart(line_chart, width="stretch")
        st.caption(
            "Biểu đồ hiển thị đủ 3 tiêu chí; trục phải dùng cho Tổng bán. Doanh thu ước tính = giá hiện tại x lượt mua."
            " Dùng lăn chuột để zoom và kéo để di chuyển theo trục thời gian."
        )

        st.markdown("### Export dữ liệu cho Looker Studio")
        line_totals_for_looker = minute_totals.copy()
        line_totals_for_looker["thoi_diem_yyyy_mm_dd_hh_mm"] = line_totals_for_looker["moc_thoi_gian"].dt.strftime(
            "%Y-%m-%d %H:%M"
        )
        line_totals_for_looker["tong_doanh_thu_uoc_tinh"] = line_totals_for_looker["tong_gia"]
        category_timeseries_for_looker = (
            trend_df.groupby(["moc_thoi_gian", "danh_muc"], as_index=False)
            .agg(
                tong_ban=("luot_mua", "sum"),
                tong_gia=("doanh_thu_uoc_tinh", "sum"),
                so_san_pham=("id_product", "nunique"),
                rating_trung_binh=("diem_danh_gia", "mean"),
            )
            .sort_values(["moc_thoi_gian", "danh_muc"])
        )
        category_timeseries_for_looker["tong_doanh_thu_uoc_tinh"] = category_timeseries_for_looker["tong_gia"]
        category_timeseries_for_looker["thoi_diem_yyyy_mm_dd_hh_mm"] = category_timeseries_for_looker[
            "moc_thoi_gian"
        ].dt.strftime("%Y-%m-%d %H:%M")
        category_summary_for_looker = category_summary[
            [
                "danh_muc",
                "so_san_pham",
                "luot_mua_tong",
                "tong_gia",
                "gia_trung_binh",
                "rating_trung_binh",
            ]
        ].sort_values("luot_mua_tong", ascending=False)
        category_summary_for_looker["tong_doanh_thu_uoc_tinh"] = category_summary_for_looker["tong_gia"]

        c1, c2 = st.columns(2)
        with c1:
            st.download_button(
                "Tải CSV Looker - line_totals",
                data=line_totals_for_looker.to_csv(index=False).encode("utf-8"),
                file_name="looker_line_totals.csv",
                mime="text/csv",
                use_container_width=True,
            )
            st.download_button(
                "Tải CSV Looker - category_timeseries",
                data=category_timeseries_for_looker.to_csv(index=False).encode("utf-8"),
                file_name="looker_category_timeseries.csv",
                mime="text/csv",
                use_container_width=True,
            )
        with c2:
            st.download_button(
                "Tải CSV Looker - category_summary",
                data=category_summary_for_looker.to_csv(index=False).encode("utf-8"),
                file_name="looker_category_summary.csv",
                mime="text/csv",
                use_container_width=True,
            )
    else:
        st.info("Không có dữ liệu để vẽ xu hướng theo danh mục với lựa chọn hiện tại.")

    lookback_days = st.selectbox("Bảng tổng hợp gần đây", [7, 30, 90], index=1)
    cutoff_time = pd.Timestamp.now() - pd.Timedelta(days=int(lookback_days))
    recent = filtered[filtered["thoi_diem"] >= cutoff_time].sort_values("thoi_diem")

    if not recent.empty:
        recent_summary = (
            recent.groupby("danh_muc", as_index=False)
            .agg(
                so_snapshot=("id_product", "count"),
                so_san_pham=("id_product", "nunique"),
                gia_trung_binh=("gia_hien_tai", "mean"),
                rating_trung_binh=("diem_danh_gia", "mean"),
                luot_mua_trung_binh=("luot_mua", "mean"),
                luot_mua_tong=("luot_mua", "sum"),
            )
            .sort_values("so_snapshot", ascending=False)
        )
        st.dataframe(recent_summary, width="stretch")

    with st.expander("📋 Xem trạng thái phủ dữ liệu 10 danh mục"):
        coverage_rows = []
        existing_categories = set(cast(pd.Series, filtered["danh_muc"]).astype(str).unique().tolist())
        for cat in DASHBOARD_TARGET_CATEGORIES:
            coverage_rows.append(
                {
                    "danh_muc": cat,
                    "co_du_lieu": cat in existing_categories,
                }
            )
        st.dataframe(pd.DataFrame(coverage_rows), width="stretch")


def main() -> None:
    st.set_page_config(page_title="Tiki Crawl Dashboard", layout="wide")
    st.title("Tiki Crawl Dashboard")
    st.caption("Cào mới, sync giá, và xem biến động dữ liệu theo snapshots")

    with st.sidebar:
        st.header("Thông tin")
        st.write(f"DB path: {RAW_DB_PATH}")
        st.write(f"DB tồn tại: {'Có' if RAW_DB_PATH.exists() else 'Chưa'}")

    tab_dashboard, tab_snapshots, tab_crawl, tab_duckdb = st.tabs(
        ["📊 Dashboard", "📈 Snapshots", "🕷️ Crawl", "🗄️ DuckDB"]
    )
    with tab_dashboard:
        render_dashboard_tab()
    with tab_snapshots:
        render_snapshot_tab()
    with tab_crawl:
        render_crawl_tab()
    with tab_duckdb:
        render_duckdb_tab(RAW_DB_PATH)


if __name__ == "__main__":
    main()
