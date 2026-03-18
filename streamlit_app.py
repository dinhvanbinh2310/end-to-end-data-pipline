import sys
from typing import cast
from pathlib import Path
from datetime import datetime, timedelta

import duckdb
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
RAW_DB_PATH = DATA_DIR / "tiki_scraped_data_raw.duckdb"

SCRAPER_DIR = BASE_DIR / "src" / "scraper-services"
sys.path.insert(0, str(SCRAPER_DIR))

try:
    from tiki_scraper import crawl_new_products, sync_prices_from_existing
except Exception:
    crawl_new_products = None
    sync_prices_from_existing = None


def filter_dataframe(df: pd.DataFrame, key: str) -> pd.DataFrame:
    if df.empty:
        return df

    search_text = st.text_input("Search", key=f"search_{key}").strip().lower()
    if not search_text:
        return df

    mask = df.astype(str).apply(lambda col: col.str.lower().str.contains(search_text, na=False))
    return df[mask.any(axis=1)]


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
    return df[wanted]


@st.cache_data(show_spinner=False)
def load_duckdb_tables() -> pd.DataFrame:
    if not RAW_DB_PATH.exists():
        return pd.DataFrame()
    with duckdb.connect(str(RAW_DB_PATH), read_only=True) as con:
        return con.execute("SHOW TABLES").fetchdf()


@st.cache_data(show_spinner=False)
def load_duckdb_preview(table_name: str, limit: int) -> pd.DataFrame:
    if not RAW_DB_PATH.exists():
        return pd.DataFrame()
    with duckdb.connect(str(RAW_DB_PATH), read_only=True) as con:
        if limit is None:
            return con.execute(f'SELECT * FROM "{table_name}"').fetchdf()
        return con.execute(f'SELECT * FROM "{table_name}" LIMIT {int(limit)}').fetchdf()


@st.cache_data(show_spinner=False)
def get_duckdb_table_row_count(table_name: str) -> int:
    if not RAW_DB_PATH.exists():
        return 0
    with duckdb.connect(str(RAW_DB_PATH), read_only=True) as con:
        row = con.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()
    return int(row[0]) if row else 0


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
        df["id_product"] = pd.to_numeric(df["id_product"], errors="coerce").astype("Int64")

    return df.dropna(subset=["thoi_diem", "id_product"])


def _safe_int(value: object, default: int = 0) -> int:
    num = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(num):
        return default
    return int(num)


def _safe_float(value: object, default: float = 0.0) -> float:
    num = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(num):
        return default
    return float(num)


def render_crawl_tab() -> None:
    st.subheader("Cào Dữ Liệu Từ Giao Diện")

    if crawl_new_products is None or sync_prices_from_existing is None:
        st.error("Không import được module tiki_scraper. Kiểm tra src/scraper-services/tiki_scraper.py")
        return

    left, right = st.columns(2)

    with left:
        with st.form("new_crawl_form"):
            st.markdown("### Cào mới theo từ khóa")
            keyword = st.text_input("Từ khóa", value="điện thoại iphone")
            danh_muc = st.text_input("Danh mục", value="giao_dien")
            quantity = st.selectbox("Số lượng sản phẩm", [10, 20, 30], index=0)
            submit_new = st.form_submit_button("Cào mới")

        if submit_new:
            if not keyword.strip():
                st.warning("Nhập từ khóa trước khi cào.")
            else:
                with st.spinner("Đang cào dữ liệu mới..."):
                    result = crawl_new_products(
                        keyword=keyword.strip(),
                        quantity=int(quantity),
                        output_dir=str(DATA_DIR),
                        danh_muc=danh_muc.strip(),
                    )
                st.success(
                    f"Đã thêm {result['inserted']}/{result['requested']} bản ghi mới vào DB."
                )
                st.cache_data.clear()

    with right:
        with st.form("sync_old_form"):
            st.markdown("### Sync giá từ sản phẩm cũ")
            max_items = st.selectbox("Số sản phẩm cần sync", [10, 20, 30, 50, 100], index=2)
            delay_seconds = st.slider("Delay mỗi request (giây)", 0.0, 1.5, 0.3, 0.1)
            submit_sync = st.form_submit_button("Sync giá")

        if submit_sync:
            with st.spinner("Đang sync giá sản phẩm cũ..."):
                result = sync_prices_from_existing(
                    output_dir=str(DATA_DIR),
                    max_items=int(max_items),
                    delay_seconds=float(delay_seconds),
                )
            if result["success"]:
                st.success(f"Sync thành công. Đã tạo bản ghi mới trong {result['db_path']}")
            else:
                st.warning("Không có bản ghi mới được tạo trong lần sync này.")
            st.cache_data.clear()

    st.markdown("---")
    st.markdown("### Tự động cào theo lịch")

    auto_enabled = st.toggle("Bật tự động cào", key="auto_crawl_enabled")
    auto_quantity = st.selectbox("Số lượng mỗi từ khóa", [10, 20, 30], index=0, key="auto_crawl_quantity")
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
                with st.spinner("Đang tự động cào dữ liệu đầu giờ..."):
                    for danh_muc, tu_khoa in parsed_targets:
                        result = crawl_new_products(
                            keyword=tu_khoa,
                            quantity=int(auto_quantity),
                            output_dir=str(DATA_DIR),
                            danh_muc=danh_muc,
                        )
                        total_inserted += int(result.get("inserted", 0))
                        total_requested += int(result.get("requested", 0))

                st.session_state["auto_crawl_last_slot"] = run_slot_key
                st.success(
                    f"Auto crawl {now.strftime('%H:%M')} hoàn tất: {total_inserted}/{total_requested} bản ghi mới."
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
        df = df[df["kieu_cao"].isin(mode_filter)]

    df = filter_dataframe(df, "snapshots")
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
    st.markdown(
        """
        <style>
        .kpi-card {
            background: linear-gradient(135deg, rgba(34, 197, 94, 0.16), rgba(14, 116, 144, 0.16));
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 12px;
            padding: 8px 12px;
            margin-bottom: 8px;
        }
        .kpi-label {
            opacity: 0.85;
            font-size: 0.85rem;
        }
        .kpi-number {
            font-size: 1.3rem;
            font-weight: 700;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.subheader("Dashboard Biến Động Sản Phẩm")
    st.caption("Theo dõi biến động giá, rating, lượt mua theo thời gian")

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

    filtered = df.copy()
    if danh_muc_filter:
        filtered = filtered[filtered["danh_muc"].astype(str).isin(danh_muc_filter)]
    if tu_khoa_filter:
        filtered = filtered[filtered["tu_khoa"].astype(str).isin(tu_khoa_filter)]
    if mode_filter and "kieu_cao" in filtered.columns:
        filtered = filtered[filtered["kieu_cao"].astype(str).isin(mode_filter)]

    if filtered.empty:
        st.warning("Không có dữ liệu sau khi lọc.")
        return

    search_name = st.text_input("Tìm tên sản phẩm", value="").strip().lower()
    if search_name:
        filtered = filtered[
            filtered["ten_san_pham"].fillna("").astype(str).str.lower().str.contains(search_name, na=False)
        ]
        if filtered.empty:
            st.warning("Không tìm thấy sản phẩm phù hợp.")
            return

    product_map = (
        filtered.sort_values("thoi_diem")
        .drop_duplicates(subset=["id_product"], keep="last")
        .loc[:, ["id_product", "ten_san_pham"]]
    )
    product_map["label"] = (
        product_map["id_product"].astype(str)
        + " | "
        + product_map["ten_san_pham"].fillna("Không tên").astype(str)
    )
    product_labels = product_map["label"].tolist()
    selected_label = cast(str, st.selectbox("Chọn sản phẩm", product_labels))
    selected_id = int(product_map.loc[product_map["label"] == selected_label, "id_product"].iloc[0])

    product_df = filtered[filtered["id_product"] == selected_id].sort_values("thoi_diem")
    latest = product_df.iloc[-1]
    previous = product_df.iloc[-2] if len(product_df) > 1 else None

    metric_a, metric_b, metric_c = st.columns(3)
    latest_price = _safe_int(latest.get("gia_hien_tai"), 0)
    previous_price = _safe_int(previous.get("gia_hien_tai"), 0) if previous is not None else None
    latest_rating = _safe_float(latest.get("diem_danh_gia"), 0.0)
    previous_rating = _safe_float(previous.get("diem_danh_gia"), 0.0) if previous is not None else None
    latest_sales = _safe_int(latest.get("luot_mua"), 0)
    previous_sales = _safe_int(previous.get("luot_mua"), 0) if previous is not None else None

    with metric_a:
        delta = None if previous_price is None else (latest_price - previous_price)
        st.markdown(
            f'<div class="kpi-card"><div class="kpi-label">Giá hiện tại</div><div class="kpi-number">{latest_price:,}</div></div>',
            unsafe_allow_html=True,
        )
        st.metric("Giá hiện tại", f"{latest_price:,}", None if delta is None else f"{int(delta):,}")
    with metric_b:
        delta = None if previous_rating is None else (latest_rating - previous_rating)
        st.markdown(
            f'<div class="kpi-card"><div class="kpi-label">Điểm đánh giá</div><div class="kpi-number">{latest_rating:.2f}</div></div>',
            unsafe_allow_html=True,
        )
        st.metric("Điểm đánh giá", f"{latest_rating:.2f}", None if delta is None else f"{float(delta):+.2f}")
    with metric_c:
        delta = None if previous_sales is None else (latest_sales - previous_sales)
        st.markdown(
            f'<div class="kpi-card"><div class="kpi-label">Lượt mua</div><div class="kpi-number">{latest_sales:,}</div></div>',
            unsafe_allow_html=True,
        )
        st.metric("Lượt mua", f"{latest_sales:,}", None if delta is None else f"{int(delta):,}")

    latest_url = str(latest.get("product_url") or "").strip()
    if latest_url.startswith("http"):
        st.markdown(f"[Mở trang sản phẩm]({latest_url})")

    metric_choices = st.multiselect(
        "Chỉ số trên biểu đồ",
        ["gia_hien_tai", "diem_danh_gia", "luot_mua"],
        default=["gia_hien_tai", "diem_danh_gia", "luot_mua"],
    )
    if metric_choices:
        plot_df = product_df.set_index("thoi_diem")[metric_choices].copy()
        rename_map = {
            "gia_hien_tai": "Giá hiện tại",
            "diem_danh_gia": "Điểm đánh giá",
            "luot_mua": "Lượt mua",
        }
        plot_df = plot_df.rename(columns=rename_map)
        st.line_chart(plot_df, height=320)

    lookback_days = st.selectbox("Bảng biến động gần đây", [7, 30, 90], index=1)
    cutoff_time = pd.Timestamp.now() - pd.Timedelta(days=int(lookback_days))
    recent = filtered[filtered["thoi_diem"] >= cutoff_time].sort_values("thoi_diem")

    if not recent.empty:
        summary = (
            recent.groupby("id_product", as_index=False)
            .agg(
                ten_san_pham=("ten_san_pham", "last"),
                gia_dau=("gia_hien_tai", "first"),
                gia_cuoi=("gia_hien_tai", "last"),
                rating_dau=("diem_danh_gia", "first"),
                rating_cuoi=("diem_danh_gia", "last"),
                luot_mua_dau=("luot_mua", "first"),
                luot_mua_cuoi=("luot_mua", "last"),
                product_url=("product_url", "last"),
                so_moc=("thoi_diem", "count"),
            )
        )
        summary["delta_gia"] = summary["gia_cuoi"] - summary["gia_dau"]
        summary["delta_rating"] = summary["rating_cuoi"] - summary["rating_dau"]
        summary["delta_luot_mua"] = summary["luot_mua_cuoi"] - summary["luot_mua_dau"]
        summary = summary.sort_values("delta_gia", key=lambda s: s.abs(), ascending=False)
        summary["chi_tiet"] = summary["product_url"]

        st.dataframe(
            summary[
                [
                    "id_product",
                    "ten_san_pham",
                    "so_moc",
                    "gia_dau",
                    "gia_cuoi",
                    "delta_gia",
                    "rating_dau",
                    "rating_cuoi",
                    "delta_rating",
                    "luot_mua_dau",
                    "luot_mua_cuoi",
                    "delta_luot_mua",
                    "chi_tiet",
                ]
            ],
            width="stretch",
            column_config={
                "chi_tiet": st.column_config.LinkColumn("Chi tiết", display_text="Mở"),
            },
        )


def render_duckdb_tab() -> None:
    st.subheader("DuckDB Explorer")
    st.caption(f"DB: {RAW_DB_PATH}")

    if not RAW_DB_PATH.exists():
        st.warning("Chưa tìm thấy file DB. Hãy cào dữ liệu trước.")
        return

    tables_df = load_duckdb_tables()
    if tables_df.empty:
        st.info("DB chưa có bảng")
        return

    st.dataframe(tables_df, width="stretch")
    table_name = cast(str, st.selectbox("Chọn bảng", tables_df["name"].tolist()))
    total_rows = get_duckdb_table_row_count(table_name)
    st.caption(f"Tổng số dòng trong bảng: {total_rows}")

    slider_key = f"duckdb_rows_slider_{table_name}"
    input_key = f"duckdb_rows_input_{table_name}"
    default_rows = min(100, total_rows)

    if slider_key not in st.session_state:
        st.session_state[slider_key] = default_rows
    if input_key not in st.session_state:
        st.session_state[input_key] = default_rows

    # Keep state valid when table changes or row counts shift.
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
            "Số dòng hiển thị (0 đến tổng số dòng)",
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
            help="Nhập giá trị tùy ý, nhấn Enter để cập nhật slider.",
        )

    limit = int(st.session_state[slider_key])
    if limit == total_rows and total_rows > 100000:
        st.warning("Bảng lớn, hiển thị toàn bộ có thể chậm. Nên dùng Search hoặc giảm số dòng preview.")

    preview_df = load_duckdb_preview(table_name=table_name, limit=limit)
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


def main() -> None:
    st.set_page_config(page_title="Tiki Crawl Dashboard", layout="wide")
    st.title("Tiki Crawl Dashboard")
    st.caption("Cào mới, sync giá, và xem biến động dữ liệu theo snapshots")

    with st.sidebar:
        st.header("Thông tin")
        st.write(f"DB path: {RAW_DB_PATH}")
        st.write(f"DB tồn tại: {'Có' if RAW_DB_PATH.exists() else 'Chưa'}")

    tab_crawl, tab_snapshots, tab_dashboard, tab_duckdb = st.tabs(["Crawl", "Snapshots", "Dashboard", "DuckDB"])
    with tab_crawl:
        render_crawl_tab()
    with tab_snapshots:
        render_snapshot_tab()
    with tab_dashboard:
        render_dashboard_tab()
    with tab_duckdb:
        render_duckdb_tab()


if __name__ == "__main__":
    main()
