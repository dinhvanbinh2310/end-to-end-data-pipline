"""
Tiki Pipeline – Custom Theme & CSS
Tập trung toàn bộ styling, palette và inject CSS tại đây.
"""

import streamlit as st

# ──────────────────────────────────────────────
# 1. Color Palette  (Dark-mode, muted & premium)
# ──────────────────────────────────────────────
COLORS = {
    # Background layers
    "bg_primary": "#0E1117",
    "bg_secondary": "#161B22",
    "bg_card": "#1C2333",
    "bg_hover": "#21283B",

    # Text
    "text_primary": "#C9D1D9",
    "text_secondary": "#8B949E",
    "text_muted": "#6E7681",

    # Accent palette
    "accent": "#6C63FF",       # Soft indigo
    "accent_hover": "#7B73FF",
    "accent_muted": "rgba(108, 99, 255, 0.15)",

    # Semantic
    "success": "#3FB950",
    "warning": "#D29922",
    "error": "#F85149",
    "info": "#58A6FF",

    # Chart palette (harmonious, not neon)
    "chart_1": "#6C63FF",  # Indigo
    "chart_2": "#3FB950",  # Green
    "chart_3": "#F0883E",  # Orange
    "chart_4": "#58A6FF",  # Blue
    "chart_5": "#BC8CFF",  # Lavender
    "chart_6": "#F778BA",  # Pink
    "chart_7": "#79C0FF",  # Light blue
    "chart_8": "#7EE787",  # Mint
    "chart_9": "#FFA657",  # Peach
    "chart_10": "#D2A8FF", # Lilac

    # Border / divider
    "border": "#30363D",
    "border_light": "#21262D",
}

CHART_PALETTE = [
    COLORS["chart_1"],
    COLORS["chart_2"],
    COLORS["chart_3"],
    COLORS["chart_4"],
    COLORS["chart_5"],
    COLORS["chart_6"],
    COLORS["chart_7"],
    COLORS["chart_8"],
    COLORS["chart_9"],
    COLORS["chart_10"],
]

# Chart line-specific colors (for the 3-metric time-series)
LINE_COLORS = {
    "revenue": "#6C63FF",
    "rating": "#F0883E",
    "sales": "#3FB950",
}


# ──────────────────────────────────────────────
# 2. Inject Custom CSS
# ──────────────────────────────────────────────
def inject_custom_css() -> None:
    """Call once at the top of main() to inject all custom styles."""
    st.markdown(
        f"""
        <style>
        /* ── Import Google Font ── */
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

        /* ── Global ── */
        html, body, [class*="css"] {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
        }}

        /* ── Main container ── */
        .stApp {{
            background-color: {COLORS["bg_primary"]};
        }}

        /* ── Sidebar ── */
        [data-testid="stSidebar"] {{
            background-color: {COLORS["bg_secondary"]} !important;
            border-right: 1px solid {COLORS["border"]} !important;
        }}

        [data-testid="stSidebar"] .stMarkdown h2 {{
            color: {COLORS["text_primary"]} !important;
            font-weight: 600 !important;
            letter-spacing: -0.02em;
        }}

        /* ── Sidebar nav buttons ── */
        [data-testid="stSidebar"] div.stButton > button {{
            justify-content: flex-start !important;
            text-align: left !important;
            padding-left: 16px !important;
            border-radius: 0px !important;
            height: 44px !important;
            border: none !important;
            transition: background-color 0.2s ease, color 0.2s ease !important;
        }}

        [data-testid="stSidebar"] div.stButton > button[kind="secondary"] {{
            background-color: transparent !important;
            color: {COLORS["text_secondary"]} !important;
        }}

        [data-testid="stSidebar"] div.stButton > button[kind="secondary"]:hover {{
            background-color: {COLORS["bg_hover"]} !important;
            color: {COLORS["text_primary"]} !important;
        }}

        [data-testid="stSidebar"] div.stButton > button[kind="primary"] {{
            background-color: {COLORS["accent_muted"]} !important;
            color: {COLORS["accent"]} !important;
            border-left: 3px solid {COLORS["accent"]} !important;
        }}

        [data-testid="stSidebar"] div.stButton > button p {{
            font-size: 14px !important;
            font-weight: 500 !important;
        }}

        /* ── Headings ── */
        h1 {{
            color: {COLORS["text_primary"]} !important;
            font-weight: 700 !important;
            letter-spacing: -0.03em;
        }}
        h2, h3 {{
            color: {COLORS["text_primary"]} !important;
            font-weight: 600 !important;
        }}

        /* ── Metric cards ── */
        [data-testid="stMetric"] {{
            background-color: {COLORS["bg_card"]} !important;
            border: 1px solid {COLORS["border"]} !important;
            border-radius: 8px !important;
            padding: 16px 20px !important;
        }}

        [data-testid="stMetricValue"] {{
            color: {COLORS["text_primary"]} !important;
            font-weight: 600 !important;
        }}

        [data-testid="stMetricLabel"] {{
            color: {COLORS["text_secondary"]} !important;
            font-size: 13px !important;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }}

        /* ── Dataframes ── */
        [data-testid="stDataFrame"] {{
            border: 1px solid {COLORS["border"]} !important;
            border-radius: 8px !important;
            overflow: hidden;
        }}

        /* ── Buttons (general) ── */
        .stButton > button {{
            border-radius: 6px !important;
            font-weight: 500 !important;
            font-size: 14px !important;
            transition: all 0.2s ease !important;
        }}

        .stButton > button[kind="primary"] {{
            background-color: {COLORS["accent"]} !important;
            border: none !important;
            color: #FFFFFF !important;
        }}

        .stButton > button[kind="primary"]:hover {{
            background-color: {COLORS["accent_hover"]} !important;
            box-shadow: 0 2px 8px rgba(108, 99, 255, 0.3) !important;
        }}

        /* ── Download buttons ── */
        .stDownloadButton > button {{
            background-color: {COLORS["bg_card"]} !important;
            border: 1px solid {COLORS["border"]} !important;
            color: {COLORS["text_primary"]} !important;
            border-radius: 6px !important;
        }}
        .stDownloadButton > button:hover {{
            background-color: {COLORS["bg_hover"]} !important;
            border-color: {COLORS["accent"]} !important;
        }}

        /* ── Form ── */
        [data-testid="stForm"] {{
            background-color: {COLORS["bg_card"]} !important;
            border: 1px solid {COLORS["border"]} !important;
            border-radius: 8px !important;
            padding: 20px !important;
        }}

        /* ── Text inputs & selects ── */
        .stTextInput > div > div > input,
        .stTextArea > div > div > textarea {{
            background-color: {COLORS["bg_secondary"]} !important;
            border: 1px solid {COLORS["border"]} !important;
            color: {COLORS["text_primary"]} !important;
            border-radius: 6px !important;
            transition: border-color 0.2s ease !important;
        }}

        .stTextInput > div > div > input:focus,
        .stTextArea > div > div > textarea:focus {{
            border-color: {COLORS["accent"]} !important;
            box-shadow: 0 0 0 2px {COLORS["accent_muted"]} !important;
        }}

        /* ── Selectbox ── */
        .stSelectbox > div > div {{
            background-color: {COLORS["bg_secondary"]} !important;
            border-color: {COLORS["border"]} !important;
            border-radius: 6px !important;
        }}

        /* ── Expander ── */
        .streamlit-expanderHeader {{
            background-color: {COLORS["bg_card"]} !important;
            border-radius: 8px !important;
            color: {COLORS["text_primary"]} !important;
        }}

        /* ── Divider ── */
        hr {{
            border-color: {COLORS["border"]} !important;
        }}

        /* ── Alerts / st.info, st.success, etc. ── */
        .stAlert {{
            border-radius: 8px !important;
        }}

        [data-testid="stNotification"] {{
            border-radius: 8px !important;
        }}

        /* ── Caption ── */
        .stCaption, [data-testid="stCaptionContainer"] {{
            color: {COLORS["text_muted"]} !important;
        }}

        /* ── Tab styling (in case we need later) ── */
        [data-baseweb="tab-list"] {{
            gap: 2px !important;
        }}

        [data-baseweb="tab"] {{
            border-radius: 6px 6px 0 0 !important;
        }}

        /* ── Scrollbar ── */
        ::-webkit-scrollbar {{
            width: 6px;
            height: 6px;
        }}

        ::-webkit-scrollbar-track {{
            background: {COLORS["bg_primary"]};
        }}

        ::-webkit-scrollbar-thumb {{
            background: {COLORS["border"]};
            border-radius: 3px;
        }}

        ::-webkit-scrollbar-thumb:hover {{
            background: {COLORS["text_muted"]};
        }}

        /* ── Multiselect tags ── */
        span[data-baseweb="tag"] {{
            background-color: {COLORS["accent_muted"]} !important;
            border-color: {COLORS["accent"]} !important;
        }}

        /* ── Toggle ── */
        [data-testid="stToggle"] label span {{
            font-weight: 500 !important;
        }}

        /* ── Slider ── */
        [data-testid="stSlider"] [data-baseweb="slider"] div[role="slider"] {{
            background-color: {COLORS["accent"]} !important;
        }}

        </style>
        """,
        unsafe_allow_html=True,
    )
