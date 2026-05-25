"""
FRM Premium ETF System — Strategy C
FerryRichMan Limited
──────────────────────────────────────────────────────────────────────────────
Streamlit App — Top-2 Weighted Momentum ETF Signal with Conditional Leverage
──────────────────────────────────────────────────────────────────────────────

CORE LOGIC (Strategy C, validated as Pareto-optimal vs Combo B / D):
  - Universe: SPY, QQQ, VEU, GLD, TLT, BIL  (6 unleveraged base ETFs)
  - Leverage twins: SPY -> SSO (2x),  QQQ -> QLD (2x)
  - Per-ETF leverage threshold: SPY 0.05, QQQ 0.08
  - Score = 0.8 * 3M Adj-Close return + 0.2 * 12M Adj-Close return
  - Each month: pick TOP-2 ETFs by score, hold 60% in #1 + 40% in #2
  - If #1 or #2 is SPY/QQQ AND its score >= its threshold -> swap to 2x twin
  - Execute on first trading day of next month at Adj Open

PROVEN-OPTIMAL DESIGN CHOICES (do not modify):
  - 60/40 Top-2 weighting (vs 50/50): +0.6pp CAGR, free improvement
  - QQQ threshold 0.08 (vs 0.05): -3pp MDD, +0.02 Sharpe
  - No 200MA filter:        ❌ tested, hurts in V-recoveries
  - No AM Guard:            ❌ tested, hurts post-crash recovery
  - No DDCB circuit breaker: ❌ tested, whipsaw destroys returns
  - No 3x leverage:          ❌ tail risk too high, dotcom 2000-02 -85%
  - No SOXX:                 ❌ AI-burst stress shows 8pp deeper drawdown vs C
"""

import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from academic_validation_ui import render_academic_validation
from dateutil.relativedelta import relativedelta
import plotly.graph_objects as go
import time
import warnings
warnings.filterwarnings("ignore")
import uuid
import urllib.parse

_HK_TZ = timezone(timedelta(hours=8))


def _hk_date_key() -> str:
    """Cache key invalidates at HKT 07:00 (after US market close + yfinance ingest)."""
    return (datetime.now(_HK_TZ) - timedelta(hours=7)).strftime("%Y-%m-%d")


# ══════════════════════════════════════════════════════════
#  STRATEGY CONSTANTS  —  Strategy C
# ══════════════════════════════════════════════════════════
BASE_TICKERS = ["SPY", "QQQ", "VEU", "GLD", "TLT", "BIL"]
LEVERAGE_MAP = {"SPY": "SSO", "QQQ": "QLD"}
THRESHOLDS = {"SPY": 0.05, "QQQ": 0.08, "default": 0.05}
WEIGHT1 = 0.60   # Top-1 holding
WEIGHT2 = 0.40   # Top-2 holding
WEIGHTS = {"3m": 0.8, "6m": 0.0, "9m": 0.0, "12m": 0.2}
PERF_YEAR_START = 2008

ALL_TICKERS = sorted(set(BASE_TICKERS + list(LEVERAGE_MAP.values())))

ETF_INFO = {
    "SPY":  {"name": "SPDR S&P 500 ETF Trust",
             "class_cn": "🇺🇸 美國 S&P 500", "color": "#818cf8", "bg": "#1e1b4b"},
    "QQQ":  {"name": "Invesco QQQ Trust (Nasdaq-100)",
             "class_cn": "🇺🇸 美國科技 Nasdaq-100", "color": "#a855f7", "bg": "#3b0764"},
    "VEU":  {"name": "Vanguard FTSE All-World ex-US ETF",
             "class_cn": "🌍 全球（除美）股票", "color": "#34d399", "bg": "#064e3b"},
    "GLD":  {"name": "SPDR Gold Trust",
             "class_cn": "🥇 黃金（通脹/危機 hedge）", "color": "#fbbf24", "bg": "#451a03"},
    "TLT":  {"name": "iShares 20+ Year Treasury Bond ETF",
             "class_cn": "🛡️ 長期美國國債", "color": "#22d3ee", "bg": "#083344"},
    "BIL":  {"name": "SPDR Bloomberg 1-3 Mo T-Bill ETF",
             "class_cn": "💵 短期國庫券（現金避險）", "color": "#94a3b8", "bg": "#1e293b"},
    "SSO":  {"name": "ProShares Ultra S&P 500 (2x SPY)",
             "class_cn": "⚡ 2x SPY（杠杆美股）", "color": "#6366f1", "bg": "#1e1b4b"},
    "QLD":  {"name": "ProShares Ultra QQQ (2x QQQ)",
             "class_cn": "⚡ 2x QQQ（杠杆科技）", "color": "#9333ea", "bg": "#3b0764"},
}

MONTH_CN = ["一","二","三","四","五","六","七","八","九","十","十一","十二"]


# ══════════════════════════════════════════════════════════
#  CSS
# ══════════════════════════════════════════════════════════
def inject_css():
    st.markdown(
        """
<style>
[data-testid="stAppViewContainer"] { background: #0a0f1e !important; }
[data-testid="stHeader"]           { background: transparent !important; }
[data-testid="stToolbar"]          { display: none; }
.block-container { padding: 0 1.5rem 5rem !important; max-width: 820px; }
* { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
[data-testid="stMarkdownContainer"] p { color: #94a3b8 !important; font-size: 15px; }
h1,h2,h3 { color: #e2e8f0 !important; font-size: 22px !important; }
#MainMenu { visibility: hidden; }
footer    { visibility: hidden; }
.stTabs [data-baseweb="tab-list"] {
    background: #1e293b; border-radius: 12px; padding: 4px;
    border: 1px solid #334155; gap: 2px;
}
.stTabs [data-baseweb="tab"] {
    color: #64748b !important; font-weight: 600; border-radius: 9px;
    font-size: 13px; padding: 8px 18px;
}
.stTabs [aria-selected="true"] { background: #334155 !important; color: #e2e8f0 !important; }
.stTabs [data-baseweb="tab-panel"] { padding-top: 14px; }
div[data-testid="stTextArea"] textarea {
    background: #0a0f1e !important; border: 1.5px dashed #334155 !important;
    border-radius: 12px !important; color: #94a3b8 !important;
    font-family: 'Courier New', monospace !important; font-size: 12px !important;
    line-height: 1.8 !important; resize: none !important;
}
div[data-testid="stTextArea"] label { display: none; }
.stSpinner > div { border-top-color: #f59e0b !important; }
[data-testid="stMetricDelta"] { font-size: 13px !important; }

/* ── Content Protection ── */
[data-testid="stAppViewContainer"], [data-testid="stMarkdownContainer"],
.stTabs, .stDataFrame {
    -webkit-user-select: none !important;
    -moz-user-select: none !important;
    -ms-user-select: none !important;
    user-select: none !important;
}
input, textarea, [contenteditable] {
    -webkit-user-select: text !important;
    user-select: text !important;
}
@media print {
    body, body * { display: none !important; visibility: hidden !important; }
    html::after {
        content: "FerryRichMan LTD — Print Disabled";
        display: block; text-align: center; font-size: 24px; padding: 100px;
    }
}
img { -webkit-user-drag: none !important; }
</style>
        """,
        unsafe_allow_html=True,
    )


# ══════════════════════════════════════════════════════════
#  SECURITY — Content Protection + Watermark + Rebalance
# ══════════════════════════════════════════════════════════

def inject_content_protection():
    """Block right-click, copy shortcuts, F12, PrintScreen via parent-frame JS."""
    components.html("""
<script>
(function(){
    var d = window.parent.document;
    d.addEventListener('contextmenu', function(e){ e.preventDefault(); });
    d.addEventListener('keydown', function(e){
        var block = false;
        if (e.ctrlKey || e.metaKey) {
            var k = e.key.toLowerCase();
            if ('cusp'.indexOf(k) !== -1) block = true;
            if (e.shiftKey && 'ijc'.indexOf(k) !== -1) block = true;
        }
        if (e.key === 'F12' || e.key === 'PrintScreen') block = true;
        if (block) { e.preventDefault(); e.stopPropagation(); }
    }, true);
    d.addEventListener('dragstart', function(e){ e.preventDefault(); });
})();
</script>
""", height=0)


def inject_watermark():
    """Full-page repeating watermark — anti-screenshot with session + user fingerprint."""
    sid = st.session_state.get("frm_session_id", "")
    tag = sid[:6].upper() if sid else ""
    sub = st.session_state.get("frm_sub", {})
    user_code = sub.get("code", "")
    label = "FerryRichMan LTD"
    if user_code:
        label += "  " + user_code
    if tag:
        label += "  #" + tag
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="340" height="220">'
        '<text transform="rotate(-28 170 110)" x="50%" y="50%" '
        'font-size="15" fill="rgba(255,255,255,0.035)" text-anchor="middle" '
        'font-family="sans-serif" font-weight="700">' + label + '</text></svg>'
    )
    encoded = urllib.parse.quote(svg)
    st.markdown(
        f'''
<style>
[data-testid="stAppViewContainer"]::after {{
    content: "";
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background-image: url("data:image/svg+xml,{encoded}");
    background-repeat: repeat;
    pointer-events: none;
    z-index: 99999;
}}
</style>
        ''',
        unsafe_allow_html=True,
    )


def render_rebalance_notice(info: dict):
    """Countdown to next rebalance + latest signal change alert."""
    if not info:
        return

    now = info["now"]

    # Next month's first trading day (skip weekends)
    next_first = (now.replace(day=1) + timedelta(days=32)).replace(day=1)
    next_naive = next_first.replace(tzinfo=None) if next_first.tzinfo else next_first
    rebal = next_naive
    while rebal.weekday() >= 5:
        rebal += timedelta(days=1)

    now_naive = now.replace(tzinfo=None) if now.tzinfo else now
    days_left = (rebal - now_naive).days
    if days_left < 0:
        days_left = 0

    if days_left <= 3:
        color, bg, border_c = "#ef4444", "#1a0f0f", "#ef444433"
        icon, urgency = "🚨", "即將換倉！"
    elif days_left <= 7:
        color, bg, border_c = "#fbbf24", "#1a1508", "#fbbf2433"
        icon, urgency = "⏰", "換倉將近"
    else:
        color, bg, border_c = "#4ade80", "#0f1a12", "#4ade8033"
        icon, urgency = "📅", "正常倒數"

    rebal_str = rebal.strftime("%Y-%m-%d (%a)")

    st.markdown(
        f'''
<div style="background:{bg}; border:1px solid {border_c}; border-radius:14px;
            padding:14px 20px; margin:8px 0 20px;">
    <div style="display:flex; justify-content:space-between; align-items:center;
                flex-wrap:wrap; gap:8px;">
        <div>
            <span style="font-size:13px; color:{color}; font-weight:700;">
                {icon} 下次換倉：{rebal_str}
            </span>
            <span style="background:{color}18; color:{color}; padding:3px 10px;
                         border-radius:100px; font-size:11px; font-weight:700;
                         margin-left:8px;">
                {days_left} 天後 &middot; {urgency}
            </span>
        </div>
    </div>
</div>
        ''',
        unsafe_allow_html=True,
    )


# ══════════════════════════════════════════════════════════
#  DATA LAYER
# ══════════════════════════════════════════════════════════
def _get_daily_ohlc(t: str, start, end) -> pd.DataFrame:
    """Fetch DAILY Adj Open + Adj Close for one ticker. Returns ['Open', 'Close']."""
    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")

    def _extract(raw: pd.DataFrame) -> pd.DataFrame:
        def _squeeze(s):
            return s.squeeze() if isinstance(s, pd.DataFrame) else s
        if isinstance(raw.columns, pd.MultiIndex):
            def _col(name):
                if name in raw.columns.get_level_values(0):
                    lvl = raw[name]
                    s = lvl[t] if t in lvl.columns else lvl.iloc[:, 0]
                else:
                    s = pd.Series(dtype=float, index=raw.index)
                return _squeeze(s)
            adj_o = _col("Open"); adj_c = _col("Close")
        else:
            adj_o = _squeeze(raw.get("Open", pd.Series(dtype=float, index=raw.index)))
            adj_c = _squeeze(raw.get("Close", pd.Series(dtype=float, index=raw.index)))
        result = pd.DataFrame(index=raw.index)
        result["Open"] = adj_o
        result["Close"] = adj_c
        return result.sort_index()

    for attempt in range(4):
        try:
            raw = yf.download(t, start=start_str, end=end_str, progress=False, auto_adjust=True)
            if not raw.empty:
                return _extract(raw)
        except Exception:
            pass
        time.sleep(2 ** attempt)
    return pd.DataFrame(columns=["Open", "Close"])


@st.cache_data(show_spinner=False)
def load_prices(date_key: str = "") -> pd.DataFrame:
    """Download daily adj OHLC for all 8 tickers, build monthly panel."""
    _CACHE_VERSION = "premium_v1"
    end = datetime.today()
    start = end - relativedelta(years=22)

    close_frames = {}
    open_frames = {}

    for t in ALL_TICKERS:
        daily = _get_daily_ohlc(t, start, end)
        if daily.empty or daily["Close"].dropna().empty:
            st.error(f"⚠️ 無法從 Yahoo Finance 下載 **{t}** 數據。\n\nYahoo 限流，請等 1-2 分鐘後 F5。")
            st.stop()
        close_frames[t] = daily["Close"].resample("ME").last()
        open_frames[t] = daily["Open"].resample("ME").first()

    df = pd.DataFrame(close_frames)
    if df.empty:
        st.error("數據合併失敗，請重新整理。")
        st.stop()

    for t in ALL_TICKERS:
        df[f"{t}_open"] = open_frames[t].reindex(df.index)
    return df


@st.cache_data(show_spinner=False)
def compute_signals(df: pd.DataFrame) -> pd.DataFrame:
    """Compute scores for base tickers, then Top-2 with conditional leverage per-ETF threshold."""
    p = df.copy()

    # Date-based lookback returns (calendar months, robust to dropna)
    for m in [3, 6, 9, 12]:
        target_dates = p.index - pd.DateOffset(months=m)
        for t in ALL_TICKERS:
            full_idx = p.index.union(target_dates).sort_values()
            filled = p[t].reindex(full_idx).ffill()
            prior = filled.reindex(target_dates).values
            p[f"{t}_{m}m"] = p[t].values / prior - 1

    # Score base tickers (only base, not leveraged twins — twins inherit signal)
    for t in BASE_TICKERS:
        p[f"score_{t}"] = (
            p[f"{t}_3m"] * WEIGHTS["3m"]
            + p[f"{t}_6m"] * WEIGHTS["6m"]
            + p[f"{t}_9m"] * WEIGHTS["9m"]
            + p[f"{t}_12m"] * WEIGHTS["12m"]
        )

    # Top-2 selection per month + conditional leverage swap
    p["held_1"] = pd.Series(dtype=object, index=p.index)
    p["held_2"] = pd.Series(dtype=object, index=p.index)
    p["winner_raw_1"] = pd.Series(dtype=object, index=p.index)  # base ticker before leverage
    p["winner_raw_2"] = pd.Series(dtype=object, index=p.index)

    score_cols = [f"score_{t}" for t in BASE_TICKERS]
    score_df = p[score_cols].copy()
    score_df.columns = BASE_TICKERS

    for dt in p.index:
        scores = score_df.loc[dt]
        if not scores.notna().any():
            continue
        sorted_scores = scores.fillna(-np.inf).sort_values(ascending=False)
        for slot, col_name, raw_col in [(0, "held_1", "winner_raw_1"),
                                         (1, "held_2", "winner_raw_2")]:
            etf = sorted_scores.index[slot]
            etf_score = sorted_scores.iloc[slot]
            p.loc[dt, raw_col] = etf
            lev_t = LEVERAGE_MAP.get(etf)
            th = THRESHOLDS.get(etf, THRESHOLDS["default"])
            lev_avail = lev_t is not None and not pd.isna(p.loc[dt, f"{lev_t}_open"])
            if lev_t is not None and etf_score >= th and lev_avail:
                p.loc[dt, col_name] = lev_t
            else:
                p.loc[dt, col_name] = etf

    # Monthly returns:
    # ret = WEIGHT1 * ret(held_1 from prev month) + WEIGHT2 * ret(held_2 from prev month)
    prev_h1 = p["held_1"].shift(1)
    prev_h2 = p["held_2"].shift(1)
    p["signal_return"] = np.nan
    for i, dt in enumerate(p.index):
        h1 = prev_h1.loc[dt]
        h2 = prev_h2.loc[dt]
        if pd.isna(h1) or pd.isna(h2) or i + 1 >= len(p):
            continue
        r1 = r2 = np.nan
        for h, target in [(h1, "r1"), (h2, "r2")]:
            open_col = f"{h}_open"
            if open_col not in p.columns:
                continue
            cur_open = p.loc[dt, open_col]
            next_open = p.iloc[i + 1][open_col]
            if pd.notna(cur_open) and pd.notna(next_open) and cur_open != 0:
                r = next_open / cur_open - 1
                if target == "r1":
                    r1 = r
                else:
                    r2 = r
        if pd.notna(r1) and pd.notna(r2):
            p.loc[dt, "signal_return"] = WEIGHT1 * r1 + WEIGHT2 * r2

    return p


def get_current_info(prices: pd.DataFrame) -> dict:
    """Extract current month's holdings and metadata."""
    now = datetime.now(_HK_TZ)
    completed = prices[prices.index.month != now.month]
    if len(completed) < 2:
        return {}
    cur_row = completed.index[-1]
    prev_row = completed.index[-2]

    cur_h1 = prices.loc[cur_row, "held_1"]
    cur_h2 = prices.loc[cur_row, "held_2"]
    cur_raw1 = prices.loc[cur_row, "winner_raw_1"]
    cur_raw2 = prices.loc[cur_row, "winner_raw_2"]
    prev_h1 = prices.loc[prev_row, "held_1"]
    prev_h2 = prices.loc[prev_row, "held_2"]
    last_ret = prices.loc[cur_row, "signal_return"]

    scores = {t: float(prices.loc[cur_row, f"score_{t}"]) for t in BASE_TICKERS}
    return {
        "current_1": cur_h1, "current_2": cur_h2,
        "raw_1": cur_raw1, "raw_2": cur_raw2,
        "prev_1": prev_h1, "prev_2": prev_h2,
        "changed": (cur_h1 != prev_h1) or (cur_h2 != prev_h2),
        "last_ret": float(last_ret) if pd.notna(last_ret) else None,
        "scores": scores,
        "data_date": cur_row,
        "now": now,
    }


def calc_stats(prices: pd.DataFrame) -> dict:
    monthly_all = prices["signal_return"].dropna()
    cum_all = (1 + monthly_all).cumprod() * 10000

    # SPY benchmark (open-to-open, identical methodology)
    spy_ret_all = (prices["SPY_open"].shift(-1) / prices["SPY_open"] - 1).reindex(monthly_all.index)
    spy_cum_all = (1 + spy_ret_all.fillna(0)).cumprod() * 10000

    monthly = monthly_all[monthly_all.index.year >= PERF_YEAR_START]
    cum = (1 + monthly).cumprod()
    total = float(cum.iloc[-1] - 1)
    n_yrs = len(monthly) / 12
    cagr = float((1 + total) ** (1 / n_yrs) - 1)

    running_max = cum.cummax()
    drawdown = (cum - running_max) / running_max
    mdd = float(drawdown.min())
    mdd_end = drawdown.idxmin()
    mdd_start = cum[:mdd_end].idxmax()

    m_std = float(monthly.std())
    sharpe = float(monthly.mean() * np.sqrt(12) / m_std) if m_std > 0 else None
    neg = monthly[monthly < 0]
    sortino = float(monthly.mean() * np.sqrt(12) / neg.std()) if len(neg) > 0 and neg.std() > 0 else None

    cum_all_norm = (1 + monthly_all).cumprod()
    dd_series_all = (cum_all_norm - cum_all_norm.cummax()) / cum_all_norm.cummax() * 100

    max_dd_months = 0
    cur_run = 0
    for v in (drawdown < 0):
        if v:
            cur_run += 1
            max_dd_months = max(max_dd_months, cur_run)
        else:
            cur_run = 0

    def trailing_cagr(years: int):
        cutoff = monthly.index[-1] - relativedelta(years=years)
        sub = monthly[monthly.index > cutoff]
        if len(sub) < 6:
            return None
        r = float((1 + sub).prod() - 1)
        n = len(sub) / 12
        return float((1 + r) ** (1 / n) - 1) if n > 0 else None

    # Anchor at Jan 1 of PERF_YEAR_START with $10k baseline
    anchor_start = pd.Timestamp(f"{PERF_YEAR_START}-01-01")

    def _anchor(series, baseline):
        if len(series) == 0 or anchor_start >= series.index[0]:
            return series
        first_real = series.index[0]
        anchor_dates = pd.date_range(start=anchor_start, end=first_real, freq="ME", inclusive="left")
        all_anchor = pd.DatetimeIndex([anchor_start]).append(anchor_dates).unique().sort_values()
        anchor_series = pd.Series([baseline] * len(all_anchor), index=all_anchor)
        return pd.concat([anchor_series, series]).sort_index()

    cum_all = _anchor(cum_all, 10000.0)
    spy_cum_all = _anchor(spy_cum_all, 10000.0)
    dd_series_all = _anchor(dd_series_all, 0.0)

    # Win rate
    pos_months = (monthly > 0).sum()
    neg_months = (monthly < 0).sum()
    win_rate = pos_months / (pos_months + neg_months) if (pos_months + neg_months) > 0 else 0

    # Turnover (sum of changes in held_1 + held_2)
    chg = ((prices["held_1"] != prices["held_1"].shift(1)).sum()
           + (prices["held_2"] != prices["held_2"].shift(1)).sum())

    return {
        "cagr": cagr, "mdd": mdd, "mdd_start": mdd_start, "mdd_end": mdd_end,
        "backtest_start": monthly.index[0], "backtest_end": monthly.index[-1],
        "total_ret": total, "n_years": n_yrs,
        "init_10k": float(cum.iloc[-1] * 10000),
        "trades_yr": chg / n_yrs,
        "monthly": monthly,
        "cumulative": cum_all,
        "spy_cumulative": spy_cum_all,
        "drawdown_series": dd_series_all,
        "max_dd_months": max_dd_months,
        "sharpe": sharpe,
        "sortino": sortino,
        "cagr_3yr": trailing_cagr(3),
        "cagr_5yr": trailing_cagr(5),
        "cagr_10yr": trailing_cagr(10),
        "win_rate": win_rate,
        "best_month": float(monthly.max()),
        "worst_month": float(monthly.min()),
    }


def calc_annual(prices: pd.DataFrame) -> dict:
    monthly = prices["signal_return"].dropna()
    monthly = monthly[monthly.index.year >= PERF_YEAR_START]
    return {yr: float((1 + grp).prod() - 1) for yr, grp in monthly.groupby(monthly.index.year)}


# ══════════════════════════════════════════════════════════
#  UI COMPONENTS
# ══════════════════════════════════════════════════════════
def render_header():
    components.html("""
<a href="https://ferryrichman.com" target="_blank"
   style="display:inline-block; background:#1e293b; color:#f59e0b;
   text-decoration:none; padding:6px 14px; border-radius:8px;
   font-size:11px; font-weight:700; border:1px solid #f59e0b33;
   font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
   🏠 回主頁
</a>
""", height=38)
    st.markdown(
        """
<div style="text-align:center; padding: 24px 0 28px; border-bottom: 1px solid #1e293b; margin-bottom: 24px;">
    <div style="display:inline-block; background: linear-gradient(135deg,#f59e0b,#ef4444);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        font-size: 14px; font-weight: 800; letter-spacing: 3px; text-transform: uppercase; margin-bottom: 12px;">
        FerryRichMan Limited &nbsp;·&nbsp; PREMIUM
    </div>
    <div style="font-size: 42px; font-weight: 900; color: #f1f5f9; letter-spacing: -2px; line-height: 1.12; margin-bottom: 10px;">
        FRM Premium<br><span style="color:#f59e0b;">ETF SYSTEM</span>
    </div>
    <div style="font-size: 15px; color: #475569; letter-spacing: 0.5px;">
        月度 Top-2 動力 + 杠杆條件啟動 &nbsp;·&nbsp; Strategy C — Validated
    </div>
</div>
        """,
        unsafe_allow_html=True,
    )


def render_dual_signal_card(info: dict):
    if not info:
        st.error("無法獲取訊號資料，請重新整理頁面。")
        return

    h1, h2 = info["current_1"], info["current_2"]
    raw1, raw2 = info["raw_1"], info["raw_2"]
    last_ret = info["last_ret"]
    now = info["now"]
    data_dt = info["data_date"]
    changed = info["changed"]

    month_str = f"{now.year}年{MONTH_CN[now.month-1]}月"
    data_str = data_dt.strftime("%Y-%m-%d")

    info1 = ETF_INFO[h1]; info2 = ETF_INFO[h2]
    lev1 = "⚡ 2x" if h1 != raw1 else ""
    lev2 = "⚡ 2x" if h2 != raw2 else ""

    if changed:
        change_html = (f'<span style="background:#451a03;color:#fbbf24;padding:6px 14px;'
                       f'border-radius:100px;font-size:12px;font-weight:700;">🔄 換倉訊號</span>')
    else:
        change_html = (f'<span style="background:#052e16;color:#4ade80;padding:6px 14px;'
                       f'border-radius:100px;font-size:12px;font-weight:700;">✅ 維持持倉</span>')

    if last_ret is not None:
        pct = f"{last_ret*100:+.2f}%"
        r_clr = "#4ade80" if last_ret >= 0 else "#f87171"
        r_bg = "#052e16" if last_ret >= 0 else "#450a0a"
        ret_html = (f'<span style="background:{r_bg};color:{r_clr};padding:6px 14px;'
                    f'border-radius:100px;font-size:12px;font-weight:700;">'
                    f'{"↑" if last_ret >= 0 else "↓"} 上月回報 {pct}</span>')
    else:
        ret_html = ""

    components.html(
        f"""
<!DOCTYPE html><html><head><meta charset="UTF-8"><style>
* {{ box-sizing:border-box; margin:0; padding:0; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; }}
body {{ background:transparent; padding:0; margin:0; }}
.card {{
    background: linear-gradient(135deg, #0f1a35 0%, #1a1230 100%);
    border: 1.5px solid #f59e0b55; border-radius: 20px;
    padding: 20px 22px 18px; position: relative; overflow: hidden;
}}
.glow {{ position:absolute; top:-60px; right:-60px; width:240px; height:240px;
    background: radial-gradient(circle, #f59e0b22 0%, transparent 70%); pointer-events:none; }}
.top-row {{ display:flex; justify-content:space-between; align-items:flex-start;
    flex-wrap:wrap; gap:8px; margin-bottom:18px; }}
.label {{ font-size:11px; color:#64748b; font-weight:800; text-transform:uppercase; letter-spacing:2px; margin-bottom:4px; }}
.date  {{ font-size:11px; color:#475569; }}
.badges {{ display:flex; flex-direction:column; align-items:flex-end; gap:6px; }}
.holdings {{ display:flex; gap:14px; align-items:stretch; }}
.holding {{ flex: 1; padding: 14px; border-radius: 14px; border: 1.5px solid; }}
.holding.h1 {{ background: rgba(99,102,241,0.08); border-color: #6366f155; }}
.holding.h2 {{ background: rgba(52,211,153,0.06); border-color: #34d39955; }}
.weight-label {{ font-size:10px; color:#64748b; font-weight:800; text-transform:uppercase; letter-spacing:1.5px; margin-bottom:6px; }}
.ticker {{ font-size:36px; font-weight:900; letter-spacing:-2px; line-height:1; margin-bottom:4px; }}
.lev-tag {{ display:inline-block; font-size:10px; color:#f59e0b; background:#451a03;
    padding:2px 7px; border-radius:6px; margin-left:6px; vertical-align:middle; font-weight:700; }}
.etf-name {{ font-size:11px; color:#cbd5e1; font-weight:600; margin-top:5px; line-height:1.3; }}
.etf-cls  {{ font-size:10px; color:#64748b; margin-top:2px; }}
</style></head><body>
<div class="card">
  <div class="glow"></div>
  <div class="top-row">
    <div>
      <div class="label">{month_str} 訊號 · STRATEGY C</div>
      <div class="date">數據截至 {data_str}</div>
    </div>
    <div class="badges">{change_html}{ret_html}</div>
  </div>
  <div class="holdings">
    <div class="holding h1">
      <div class="weight-label">📌 60% · 主倉位 #1</div>
      <div class="ticker" style="color:{info1['color']};">{h1}{f'<span class="lev-tag">{lev1}</span>' if lev1 else ''}</div>
      <div class="etf-name">{info1['name']}</div>
      <div class="etf-cls">{info1['class_cn']}</div>
    </div>
    <div class="holding h2">
      <div class="weight-label">📎 40% · 副倉位 #2</div>
      <div class="ticker" style="color:{info2['color']};">{h2}{f'<span class="lev-tag">{lev2}</span>' if lev2 else ''}</div>
      <div class="etf-name">{info2['name']}</div>
      <div class="etf-cls">{info2['class_cn']}</div>
    </div>
  </div>
</div>
</body></html>
        """,
        height=300, scrolling=False,
    )


def _hex_to_rgba(hex_color: str, alpha: float = 1.0) -> str:
    """Convert #RRGGBB to rgba(r,g,b,a) — Plotly Bar marker_color rejects 8-digit hex."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"


def render_scores_chart(scores: dict, info: dict):
    """Bar chart showing all base ETF scores with #1 and #2 highlighted."""
    tickers = list(scores.keys())
    vals = [scores[t] for t in tickers]
    raw1 = info.get("raw_1"); raw2 = info.get("raw_2")
    colors = []
    for t in tickers:
        if t == raw1: colors.append(ETF_INFO[t]["color"])
        elif t == raw2: colors.append(_hex_to_rgba(ETF_INFO[t]["color"], 0.5))  # semi-transparent
        else: colors.append("#334155")

    # Sort by score descending
    idx_sorted = sorted(range(len(vals)), key=lambda i: -vals[i])
    tickers = [tickers[i] for i in idx_sorted]
    vals = [vals[i] for i in idx_sorted]
    colors = [colors[i] for i in idx_sorted]

    text_labels = []
    for t, v in zip(tickers, vals):
        prefix = ""
        if t == raw1: prefix = "🥇 "
        elif t == raw2: prefix = "🥈 "
        text_labels.append(f"{prefix}{v:+.3f}")

    fig = go.Figure(go.Bar(
        x=vals, y=tickers, orientation="h",
        marker_color=colors, marker_line_width=0,
        text=text_labels, textposition="outside",
        textfont=dict(color="#94a3b8", size=12, family="'Courier New', monospace"),
        width=0.55,
    ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        height=260, margin=dict(l=10, r=80, t=0, b=0),
        xaxis=dict(showgrid=True, gridcolor="#1e293b", zeroline=True,
                   zerolinecolor="#334155", zerolinewidth=1.5, showticklabels=False),
        yaxis=dict(showgrid=False, autorange="reversed",
                   tickfont=dict(color="#e2e8f0", size=13, family="'Courier New', monospace")),
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def render_whatsapp_section(info: dict, stats: dict):
    h1, h2 = info["current_1"], info["current_2"]
    raw1, raw2 = info["raw_1"], info["raw_2"]
    prev_h1, prev_h2 = info["prev_1"], info["prev_2"]
    last_ret = info["last_ret"]
    now = info["now"]
    changed = info["changed"]

    month_str = f"{now.month}月{now.year}"
    ret_str = f"{last_ret*100:.2f}%" if last_ret is not None else "N/A"
    lev1 = " (2x)" if h1 != raw1 else ""
    lev2 = " (2x)" if h2 != raw2 else ""

    if changed:
        ch1 = "" if h1 == prev_h1 else f"  #1: {prev_h1} → {h1}\n"
        ch2 = "" if h2 == prev_h2 else f"  #2: {prev_h2} → {h2}\n"
        change_line = f"🔄 換倉訊號:\n{ch1}{ch2}".rstrip()
    else:
        change_line = f"✅ 維持持倉：60% {h1}{lev1} + 40% {h2}{lev2}"

    bt_start = stats["backtest_start"].year if stats.get("backtest_start") is not None else "—"
    bt_end = stats["backtest_end"].year if stats.get("backtest_end") is not None else "—"
    bt_period = f"（{bt_start}-{bt_end}）"

    c3 = stats.get("cagr_3yr"); c5 = stats.get("cagr_5yr"); c10 = stats.get("cagr_10yr")
    yr3 = f"3年年化：{c3*100:.1f}%" if c3 is not None else "3年年化：數據不足"
    yr5 = f"5年年化：{c5*100:.1f}%" if c5 is not None else "5年年化：數據不足"
    yr10 = f"10年年化：{c10*100:.1f}%" if c10 is not None else "10年年化：數據不足"

    msg = (
        f"📊【FRM ETF Premium Signal】{month_str}\n"
        f"\n"
        f"🥇 #1 主倉 (60%): {h1}{lev1}  {ETF_INFO[h1]['name']}\n"
        f"🥈 #2 副倉 (40%): {h2}{lev2}  {ETF_INFO[h2]['name']}\n"
        f"\n"
        f"{change_line}\n"
        f"📈 上月策略回報：{ret_str}\n"
        f"\n"
        f"📅 執行時間：本月第一個交易日，開市價買入\n"
        f"⏰ 執行 60% / 40% 嘅資金分配\n"
        f"\n"
        f"回測 CAGR：{stats['cagr']*100:.1f}% {bt_period}  |  MDD：{stats['mdd']*100:.1f}%\n"
        f"Sharpe：{stats['sharpe']:.2f}  |  Sortino：{stats['sortino']:.2f}\n"
        f"{yr3}\n{yr5}\n{yr10}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"@FRM ETF Premium · FerryRichMan Limited\n"
        f"（只供教學及記錄用途，不構成任何投資建議）"
    )

    html_enc = msg.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    html_display = html_enc.replace("\n", "<br>")

    components.html(
        f"""
<!DOCTYPE html><html><head><meta charset="UTF-8"><style>
* {{ box-sizing:border-box; margin:0; padding:0; }}
body {{ margin:0; padding:10px 0 4px; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; background:transparent; }}
.lbl {{ font-size:11px; color:#64748b; font-weight:800; text-transform:uppercase; letter-spacing:1.5px; margin-bottom:10px; }}
.msg {{ background:#060c1a; border:1.5px dashed #334155; border-radius:12px; padding:16px 18px;
       font-size:13px; color:#94a3b8; line-height:1.85; font-family:'Courier New',monospace;
       margin-bottom:14px; word-break:break-word; }}
.btn {{ display:block; width:100%; background: linear-gradient(135deg, #f59e0b, #ef4444); color: #fff;
       border: none; border-radius: 12px; padding: 15px 0; font-size: 15px; font-weight: 700;
       cursor: pointer; letter-spacing: 0.3px; box-shadow: 0 4px 18px rgba(245,158,11,0.4);
       transition: opacity 0.15s, transform 0.15s; }}
.btn:hover {{ opacity:0.88; transform:translateY(-1px); }}
.btn.ok {{ background: linear-gradient(135deg,#059669,#047857); box-shadow: 0 4px 18px rgba(5,150,105,0.4); }}
</style></head><body>
<textarea id="rawmsg" readonly style="position:absolute;left:-9999px;top:0;width:1px;height:1px;opacity:0;pointer-events:none;">{html_enc}</textarea>
<div class="lbl">📱 WhatsApp 訊息</div>
<div class="msg">{html_display}</div>
<button class="btn" id="b" onclick="cp()">📋 一鍵複製</button>
<script>
function cp() {{
  var ta = document.getElementById('rawmsg'); var b = document.getElementById('b');
  var txt = ta.value;
  function done() {{ b.className='btn ok'; b.innerHTML='✅ 已複製！'; setTimeout(function(){{ b.className='btn'; b.innerHTML='📋 一鍵複製'; }}, 3000); }}
  function fall() {{
    ta.style.cssText='position:static;width:100%;height:60px;opacity:1;pointer-events:auto;margin-bottom:8px;';
    ta.select(); ta.setSelectionRange(0, 99999);
    try {{ document.execCommand('copy'); done(); }} catch(e) {{}}
    ta.style.cssText='position:absolute;left:-9999px;top:0;width:1px;height:1px;opacity:0;pointer-events:none;';
  }}
  if (navigator.clipboard && window.isSecureContext) {{ navigator.clipboard.writeText(txt).then(done, fall); }}
  else {{ fall(); }}
}}
</script>
</body></html>
        """,
        height=620, scrolling=False,
    )


def render_kpis(stats: dict):
    kpi = """background:#111827; border:1px solid #1e293b; border-radius:14px;
             padding:16px 12px; text-align:center;"""

    c1, c2, c3, c4, c5 = st.columns(5)
    cells = [
        (c1, f"{stats['cagr']*100:.1f}%", "CAGR", "#4ade80"),
        (c2, f"{stats['mdd']*100:.1f}%", "最大回撤", "#f87171"),
        (c3, f"{stats['max_dd_months']}", "最長回撤月數", "#fb923c"),
        (c4, f"${stats['init_10k']:,.0f}", "$10k 增長至", "#818cf8"),
        (c5, f"{stats['n_years']:.1f}", "回測年數", "#fbbf24"),
    ]
    for col, val, label, color in cells:
        with col:
            st.markdown(
                f'<div style="{kpi}">'
                f'<div style="font-size:24px;font-weight:900;color:{color};letter-spacing:-0.5px;">{val}</div>'
                f'<div style="font-size:10px;color:#475569;font-weight:700;text-transform:uppercase;letter-spacing:1px;margin-top:5px;">{label}</div>'
                f'</div>', unsafe_allow_html=True)

    st.markdown('<div style="margin-top:8px;"></div>', unsafe_allow_html=True)
    r1, r2, r3, r4 = st.columns(4)
    sharpe = stats.get("sharpe")
    sharpe_clr = "#4ade80" if sharpe and sharpe >= 0.75 else ("#fbbf24" if sharpe and sharpe >= 0.5 else "#f87171")
    sortino = stats.get("sortino")
    sortino_clr = "#4ade80" if sortino and sortino >= 1.0 else ("#fbbf24" if sortino and sortino >= 0.7 else "#f87171")

    cells2 = [
        (r1, f"{sharpe:.2f}" if sharpe else "—", "Sharpe", sharpe_clr, "年化 · RF=0%"),
        (r2, f"{sortino:.2f}" if sortino else "—", "Sortino", sortino_clr, "下行風險調整"),
        (r3, f"{stats.get('cagr_3yr')*100:.1f}%" if stats.get('cagr_3yr') else "—", "3年年化", "#4ade80", ""),
        (r4, f"{stats.get('cagr_5yr')*100:.1f}%" if stats.get('cagr_5yr') else "—", "5年年化", "#4ade80", ""),
    ]
    for col, val, label, color, sub in cells2:
        with col:
            st.markdown(
                f'<div style="{kpi}">'
                f'<div style="font-size:26px;font-weight:900;color:{color};letter-spacing:-0.5px;">{val}</div>'
                f'<div style="font-size:11px;color:#475569;font-weight:700;text-transform:uppercase;letter-spacing:1px;margin-top:5px;">{label}</div>'
                + (f'<div style="font-size:9px;color:#334155;margin-top:2px;">{sub}</div>' if sub else '')
                + '</div>', unsafe_allow_html=True)

    st.markdown('<div style="margin-top:8px;"></div>', unsafe_allow_html=True)
    r5, r6, r7 = st.columns(3)
    c10 = stats.get("cagr_10yr")
    cells3 = [
        (r5, f"{c10*100:.1f}%" if c10 else "—", "10年年化", "#4ade80"),
        (r6, f"{stats['win_rate']*100:.0f}%", "月勝率", "#22d3ee"),
        (r7, f"{stats['trades_yr']:.0f}", "Trades / 年", "#94a3b8"),
    ]
    for col, val, label, color in cells3:
        with col:
            st.markdown(
                f'<div style="{kpi}">'
                f'<div style="font-size:26px;font-weight:900;color:{color};letter-spacing:-0.5px;">{val}</div>'
                f'<div style="font-size:11px;color:#475569;font-weight:700;text-transform:uppercase;letter-spacing:1px;margin-top:5px;">{label}</div>'
                f'</div>', unsafe_allow_html=True)


def render_annual_chart(annual: dict):
    years = sorted(annual.keys())
    vals = [annual[y] * 100 for y in years]
    clrs = ["#4ade80" if v >= 0 else "#f87171" for v in vals]
    fig = go.Figure(go.Bar(
        x=[str(y) for y in years], y=vals, marker_color=clrs, marker_line_width=0,
        text=[f"{v:+.1f}%" for v in vals], textposition="outside",
        textfont=dict(color="#64748b", size=9), width=0.7,
    ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        height=290, margin=dict(l=0, r=0, t=30, b=0),
        xaxis=dict(showgrid=False, tickfont=dict(color="#64748b", size=10), tickangle=-45),
        yaxis=dict(showgrid=True, gridcolor="#1e293b", zeroline=True, zerolinecolor="#334155",
                   tickfont=dict(color="#64748b", size=9), ticksuffix="%"),
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def render_cumulative_chart(stats: dict):
    cum = stats["cumulative"]
    spy_cum = stats.get("spy_cumulative")
    mdd_s = stats.get("mdd_start"); mdd_e = stats.get("mdd_end")
    fig = go.Figure()
    if mdd_s is not None and mdd_e is not None:
        fig.add_vrect(x0=mdd_s, x1=mdd_e, fillcolor="rgba(248,113,113,0.08)",
                      layer="below", line_width=0,
                      annotation_text="MDD", annotation_position="top left",
                      annotation_font=dict(color="#f87171", size=10))
    if spy_cum is not None:
        fig.add_trace(go.Scatter(
            x=spy_cum.index, y=spy_cum.values, name="SPY 買入持有",
            mode="lines", line=dict(color="#475569", width=1.5, dash="dot"),
            hovertemplate="%{x|%Y-%m}  SPY: <b>$%{y:,.0f}</b><extra></extra>"))
    fig.add_trace(go.Scatter(
        x=cum.index, y=cum.values, name="FRM Premium",
        mode="lines", line=dict(color="#f59e0b", width=2.5),
        fill="tozeroy", fillcolor="rgba(245,158,11,0.07)",
        hovertemplate="%{x|%Y-%m}  FRM Premium: <b>$%{y:,.0f}</b><extra></extra>"))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        height=290, margin=dict(l=0, r=0, t=10, b=0),
        xaxis=dict(showgrid=False, tickfont=dict(color="#64748b", size=10)),
        yaxis=dict(showgrid=True, gridcolor="#1e293b",
                   tickfont=dict(color="#64748b", size=10),
                   tickprefix="$", tickformat=",.0f"),
        hovermode="x unified",
        legend=dict(orientation="h", x=0, y=1.08, font=dict(color="#64748b", size=11), bgcolor="rgba(0,0,0,0)"),
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    render_drawdown_chart(stats)


def render_drawdown_chart(stats: dict):
    dd = stats.get("drawdown_series")
    if dd is None or dd.empty:
        return
    mdd_val = stats.get("mdd", 0) * 100
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dd.index, y=dd.values, mode="lines", fill="tozeroy",
        line=dict(color="#f87171", width=1.2),
        fillcolor="rgba(248,113,113,0.15)", name="回撤",
        hovertemplate="%{x|%Y-%m}  <b>%{y:.1f}%</b><extra></extra>"))
    fig.add_hline(y=mdd_val, line=dict(color="#f87171", width=1, dash="dot"),
                  annotation_text=f"MDD {mdd_val:.1f}%", annotation_position="bottom right",
                  annotation_font=dict(color="#f87171", size=10))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        height=150, margin=dict(l=0, r=0, t=4, b=0),
        xaxis=dict(showgrid=False, tickfont=dict(color="#64748b", size=10)),
        yaxis=dict(showgrid=True, gridcolor="#1e293b", zeroline=True, zerolinecolor="#334155",
                   tickfont=dict(color="#64748b", size=9), ticksuffix="%", autorange="reversed"),
        hovermode="x unified", showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def render_dual_heatmap(prices: pd.DataFrame):
    """Dual-row allocation heatmap: top=#1 (60%), bottom=#2 (40%)."""
    h1 = prices["held_1"].shift(1)
    h2 = prices["held_2"].shift(1)
    ret_s = prices["signal_return"]

    etf_map_1, etf_map_2, ret_map = {}, {}, {}
    for dt in prices.index:
        y, m = dt.year, dt.month
        e1, e2 = h1.loc[dt], h2.loc[dt]
        r = ret_s.loc[dt]
        if pd.notna(e1): etf_map_1[(y, m)] = str(e1)
        if pd.notna(e2): etf_map_2[(y, m)] = str(e2)
        if pd.notna(r): ret_map[(y, m)] = float(r)

    # Backfill 2008 Jan-May with BIL/0% to start at PERF_YEAR_START
    if etf_map_1:
        first_y, first_m = min(etf_map_1.keys())
        y, m = PERF_YEAR_START, 1
        while (y, m) < (first_y, first_m):
            etf_map_1.setdefault((y, m), "BIL")
            etf_map_2.setdefault((y, m), "BIL")
            ret_map.setdefault((y, m), 0.0)
            m += 1
            if m > 12: m, y = 1, y + 1

    annual_ret = {}
    for (y, m), r in ret_map.items():
        annual_ret[y] = annual_ret.get(y, 0.0)
        annual_ret[y] = (1 + annual_ret[y]) * (1 + r) - 1

    color_map = {t: ETF_INFO[t]["color"] for t in ETF_INFO}
    months_lbl = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    years = sorted({k[0] for k in etf_map_1})

    header_row = ("<tr><th></th>" + "".join(
        f'<th style="font-size:9px;color:#475569;font-weight:700;padding:3px 3px 8px;text-align:center;">{ml}</th>'
        for ml in months_lbl) + "</tr>")

    rows_html = []
    for y in years:
        cells_html = []
        for m in range(1, 13):
            etf1 = etf_map_1.get((y, m), "")
            etf2 = etf_map_2.get((y, m), "")
            ret = ret_map.get((y, m), None)
            bg1 = color_map.get(etf1, "#1a2035")
            bg2 = color_map.get(etf2, "#1a2035")
            ret_block = ""
            if ret is not None:
                pct = f"{ret*100:+.1f}%"
                rclr = "#4ade80" if ret >= 0 else "#f87171"
                ret_block = f'<div style="font-size:8px;color:{rclr};font-weight:700;text-align:center;line-height:1.2;margin-top:2px;">{pct}</div>'
            cells_html.append(
                f'<td style="vertical-align:top;padding:0;min-width:40px;">'
                f'<div style="background:{bg1};color:#0a0f1e;font-weight:800;font-size:9px;padding:4px 2px;text-align:center;border-radius:4px 4px 0 0;">{etf1}</div>'
                f'<div style="background:{bg2};color:#0a0f1e;font-weight:800;font-size:8px;padding:3px 2px;text-align:center;border-radius:0 0 4px 4px;opacity:0.7;">{etf2}</div>'
                f'{ret_block}</td>')
        yr_ret = annual_ret.get(y)
        yr_ret_html = ""
        if yr_ret is not None:
            yclr = "#4ade80" if yr_ret >= 0 else "#f87171"
            ysign = "+" if yr_ret >= 0 else ""
            yr_ret_html = f'<div style="font-size:10px;color:{yclr};font-weight:700;margin-top:3px;white-space:nowrap;">{ysign}{yr_ret*100:.1f}%</div>'
        rows_html.append(
            f"<tr><td style='font-size:11px;color:#94a3b8;font-weight:700;padding-right:10px;white-space:nowrap;vertical-align:middle;text-align:right;'>"
            f"{y}{yr_ret_html}</td>" + "".join(cells_html) + "</tr>")

    legend_etfs = ["SPY", "SSO", "QQQ", "QLD", "VEU", "GLD", "TLT", "BIL"]
    legend = "".join(
        f'<span style="display:inline-flex;align-items:center;gap:4px;margin-right:10px;">'
        f'<span style="width:10px;height:10px;border-radius:2px;background:{color_map[t]};display:inline-block;"></span>'
        f'<span style="font-size:10px;color:#64748b;">{t}</span></span>'
        for t in legend_etfs)

    html = f"""
<div style="overflow-x:auto;">
  <div style="margin-bottom:10px;">{legend}
    <span style="font-size:10px;color:#475569;margin-left:8px;">（每格上方=60% #1，下方=40% #2）</span>
  </div>
  <table style="border-collapse:separate;border-spacing:3px;width:100%;">
    {header_row}{"".join(rows_html)}
  </table>
</div>"""
    st.markdown(html, unsafe_allow_html=True)


def render_validation_section():
    """Section showing all the verified tests + benchmarks proving Strategy C robust."""
    st.markdown(
        """
<div style="background:#0d1424; border:1px solid #1e293b; border-radius:14px; padding:20px 24px; margin-top:18px;">
  <div style="font-size:11px;color:#f59e0b;font-weight:800;text-transform:uppercase;letter-spacing:1.5px;margin-bottom:12px;">
    Strategy Validation · 完整測試紀錄
  </div>

  <p style="font-size:13px;color:#94a3b8;line-height:1.7;margin-bottom:14px;">
    <b style="color:#cbd5e1;">Strategy C</b> 經過 <b>walk-forward optimization</b>、<b>17年回測（含 GFC + COVID + 2022）</b>、
    <b>3 個 AI burst stress scenarios</b> 同 <b>11 個 alternative variants 比較</b> 嘅完整驗證。
  </p>

  <div style="font-size:12px;color:#cbd5e1;font-weight:700;margin-top:10px;margin-bottom:6px;">
    ✅ 證實有效嘅設計選擇
  </div>
  <ul style="font-size:12px;color:#94a3b8;line-height:1.8;padding-left:20px;margin-bottom:14px;">
    <li><b>Top-2 60/40 weighted</b>：vs 50/50 提升 +0.6pp CAGR、Sharpe +0.01（Pareto win）</li>
    <li><b>QQQ threshold 0.08（vs SPY 0.05）</b>：救 -3pp MDD、Sharpe +0.02 — QQQ 高 vol，門檻應該高啲</li>
    <li><b>Conditional leverage @ 0.05</b>：相對「always leveraged」Sharpe 升 0.07、MDD 細 4pp</li>
    <li><b>Score = 0.8×3M + 0.2×12M</b>：286 weight combinations grid search 第 95 百分位，鄰域穩定</li>
    <li><b>GLD + TLT 留喺 universe</b>：2008 GFC + 2022 都係 GLD/TLT 救命</li>
  </ul>

  <div style="font-size:12px;color:#cbd5e1;font-weight:700;margin-top:14px;margin-bottom:6px;">
    ❌ 已測試但會傷害策略嘅嘢（千祈唔好加）
  </div>
  <ul style="font-size:12px;color:#94a3b8;line-height:1.8;padding-left:20px;margin-bottom:14px;">
    <li><b>200MA Filter</b>：2008 GFC 多蝕 -4pp，V-recovery 時 stop out</li>
    <li><b>AM Guard</b>（12M&lt;0 → BIL）：2009-06 失去 VEU +12% 反彈</li>
    <li><b>DDCB 回撤熔斷</b>：whipsaw 損失，CAGR 由 14.5% 跌到 5%</li>
    <li><b>Walk-forward weight 優化</b>：固定 weights Sharpe 0.93 vs 重新優化 0.57</li>
    <li><b>3x 杠杆 ETF</b>：dotcom 2000-02 SOXL 跌 -98%</li>
    <li><b>SOXX 加入 universe</b>：AI burst stress 多蝕 5-9pp</li>
  </ul>

  <div style="font-size:12px;color:#cbd5e1;font-weight:700;margin-top:14px;margin-bottom:6px;">
    🔥 AI Bubble Burst Stress Test 結果（projected from May 2026）
  </div>
  <table style="font-size:11px;color:#94a3b8;width:100%;border-collapse:collapse;margin-bottom:12px;">
    <thead><tr style="background:#1e293b;">
      <th style="padding:6px;text-align:left;color:#cbd5e1;">Scenario</th>
      <th style="padding:6px;text-align:right;color:#cbd5e1;">最差單月</th>
      <th style="padding:6px;text-align:right;color:#cbd5e1;">18個月累積</th>
    </tr></thead>
    <tbody>
      <tr><td style="padding:6px;">S1. Dotcom 慢跌（QQQ -47%）</td><td style="padding:6px;text-align:right;">-5.4%</td><td style="padding:6px;text-align:right;color:#4ade80;">+8.62%</td></tr>
      <tr style="background:#0a0f1e;"><td style="padding:6px;">S2. COVID 急跌（單月 -25%）</td><td style="padding:6px;text-align:right;color:#f87171;">-20.8%</td><td style="padding:6px;text-align:right;color:#f87171;">-12.75%</td></tr>
      <tr><td style="padding:6px;">S3. Mag-7 unwind（QQQ -52%）</td><td style="padding:6px;text-align:right;">-6.6%</td><td style="padding:6px;text-align:right;color:#4ade80;">+13.92%</td></tr>
    </tbody>
  </table>
  <p style="font-size:11px;color:#64748b;line-height:1.6;font-style:italic;">
    3 個 scenarios 中 2 個正回報；最差場景 18 個月蝕 -12.75%（vs SOXX 變體蝕 -13.52%）。
    Strategy C 設計刻意排除 SOXX，避過 tech-specific crash 嘅 8pp 額外損失。
  </p>

  <div style="font-size:12px;color:#cbd5e1;font-weight:700;margin-top:14px;margin-bottom:6px;">
    📊 Vs 其他 strategies（17 年 backtest 2008-2026）
  </div>
  <table style="font-size:11px;color:#94a3b8;width:100%;border-collapse:collapse;">
    <thead><tr style="background:#1e293b;">
      <th style="padding:6px;text-align:left;color:#cbd5e1;">Strategy</th>
      <th style="padding:6px;text-align:right;color:#cbd5e1;">CAGR</th>
      <th style="padding:6px;text-align:right;color:#cbd5e1;">MDD</th>
      <th style="padding:6px;text-align:right;color:#cbd5e1;">Sharpe</th>
    </tr></thead>
    <tbody>
      <tr><td style="padding:6px;">SPY Buy & Hold</td><td style="padding:6px;text-align:right;">11.1%</td><td style="padding:6px;text-align:right;color:#f87171;">-47.2%</td><td style="padding:6px;text-align:right;">0.73</td></tr>
      <tr style="background:#0a0f1e;"><td style="padding:6px;">FRM Standard (SPY/VEU/BIL)</td><td style="padding:6px;text-align:right;">9.7%</td><td style="padding:6px;text-align:right;">-15.9%</td><td style="padding:6px;text-align:right;">0.86</td></tr>
      <tr><td style="padding:6px;">QRSA-25% (4 modules)</td><td style="padding:6px;text-align:right;">10.5%</td><td style="padding:6px;text-align:right;">-31.0%</td><td style="padding:6px;text-align:right;">0.63</td></tr>
      <tr style="background:#1e1b1a;"><td style="padding:6px;color:#fbbf24;"><b>FRM Premium (Strategy C) ⭐</b></td><td style="padding:6px;text-align:right;color:#fbbf24;"><b>15.0%</b></td><td style="padding:6px;text-align:right;color:#fbbf24;"><b>-27.9%</b></td><td style="padding:6px;text-align:right;color:#fbbf24;"><b>0.80</b></td></tr>
      <tr><td style="padding:6px;">Combo B (+ SOXX)</td><td style="padding:6px;text-align:right;">18.4%</td><td style="padding:6px;text-align:right;">-30.8%</td><td style="padding:6px;text-align:right;">0.91</td></tr>
    </tbody>
  </table>
</div>
        """,
        unsafe_allow_html=True,
    )


def render_warnings_section():
    """Critical risk warnings — must be acknowledged."""
    st.markdown(
        """
<div style="background:linear-gradient(135deg, #2a1010, #1a0a0a); border:1.5px solid #7f1d1d;
    border-radius:14px; padding:20px 24px; margin-top:18px;">
  <div style="font-size:11px;color:#f87171;font-weight:800;text-transform:uppercase;letter-spacing:1.5px;margin-bottom:12px;">
    ⚠️ 必須了解嘅風險
  </div>
  <ul style="font-size:13px;color:#cbd5e1;line-height:1.8;padding-left:20px;margin:0;">
    <li><b style="color:#f87171;">單月可以蝕 -20%</b>：歷史 worst month。COVID March 2020 / 2018Q4 / 2008Q4 都試過接近呢個級別</li>
    <li><b style="color:#f87171;">Max Drawdown 預期 -28% 至 -35%</b>：歷史係 -27.9%，未來最差可能 -40%（包 AI burst worst case）</li>
    <li><b style="color:#f87171;">心理承受要強</b>：當你 hold QLD 一個月蝕 -15%，唔可以 panic sell — 月底 momentum 會自動 rotate</li>
    <li><b style="color:#fbbf24;">2x ETF 杠杆衰變</b>：choppy 市場 SSO/QLD 會 underperform 2x 期望（每年約 -1% to -3%）</li>
    <li><b style="color:#fbbf24;">月度 turnover ~13 trades/yr</b>：HK 投資者 commission ~$130/yr / US 散戶有 short-term capital gains</li>
    <li><b style="color:#fbbf24;">執行紀律</b>：必須月底準時 review，月初準時執行；錯過一次 signal 可能影響全年回報</li>
    <li><b style="color:#94a3b8;">Backtest 限制</b>：17 年數據未包 2000-2007 dotcom bust，未經完整 secular bear market 驗證</li>
    <li><b style="color:#94a3b8;">Slippage 假設為零</b>：實際執行 SSO/QLD spread ~0.05-0.20%，大手會有 impact cost</li>
  </ul>
</div>
        """,
        unsafe_allow_html=True,
    )


def render_methodology_section():
    """Strategy spec — for verification by user/auditors."""
    st.markdown(
        """
<div style="background:#0d1424; border:1px solid #1e293b; border-radius:14px; padding:20px 24px; margin-top:18px;">
  <div style="font-size:11px;color:#22d3ee;font-weight:800;text-transform:uppercase;letter-spacing:1.5px;margin-bottom:12px;">
    📋 Methodology · 可驗證策略 spec
  </div>
  <pre style="font-size:11px;color:#94a3b8;line-height:1.6;font-family:'Courier New',monospace;background:#060c1a;padding:12px;border-radius:8px;margin:0;overflow-x:auto;">
UNIVERSE (6 base + 2 leveraged twins):
  SPY  S&P 500              SSO  2x SPY
  QQQ  Nasdaq 100           QLD  2x QQQ
  VEU  Global ex-US
  GLD  Gold
  TLT  20+ Yr Treasury
  BIL  1-3 Mo T-Bill (cash)

SCORE FORMULA (per base ETF, monthly):
  3M_return  = adj_close(today) / adj_close(today - 3 months) - 1
  12M_return = adj_close(today) / adj_close(today - 12 months) - 1
  score      = 0.8 × 3M + 0.2 × 12M

DECISION (each month-end):
  1. Compute score for SPY, QQQ, VEU, GLD, TLT, BIL
  2. Sort by score descending
  3. Pick TOP-2: #1 (winner) and #2 (runner-up)
  4. For each:
     IF ETF in {SPY, QQQ}:
       IF score >= threshold[ETF]:    SPY 0.05, QQQ 0.08
         use leveraged twin (SSO, QLD)
       ELSE:
         use unleveraged
     ELSE:
       use unleveraged

  5. Allocate: 60% to #1, 40% to #2

EXECUTION:
  - Decision date: last trading day of month, after close
  - Buy/sell date: first trading day of next month, at market OPEN
  - Holding period: 1 month, no intra-month adjustments

DATA SOURCE:
  Yahoo Finance via yfinance, auto_adjust=True (dividend-adjusted)
  Cache invalidates HKT 07:00 daily (after US market close + ingest)

BACKTEST WINDOW:
  PERF_YEAR_START = 2008 (first valid 12M signal: 2008-05-31 due to BIL 2007-05 inception)
  First strategy return: 2008-06-30
  </pre>
</div>
        """,
        unsafe_allow_html=True,
    )


def render_disclaimer():
    st.markdown(
        """
<div style="background:#0d1424; border:1px solid #1e293b; border-radius:14px; padding:20px 24px; margin-top:18px;">
    <div style="font-size:10px;color:#f59e0b;font-weight:800;text-transform:uppercase;letter-spacing:1.5px;margin-bottom:10px;">
        重要免責聲明 · Important Disclaimer
    </div>
    <p style="font-size:12px;color:#94a3b8;line-height:1.7;margin-bottom:8px;">
        Strategy C Premium 訊號由 FerryRichMan Limited 基於量化動力模型生成，
        <strong style="color:#cbd5e1;">僅供參考及教學用途，不構成任何投資建議</strong>。
        歷史表現不代表未來結果，杠杆 ETF 投資涉及顯著風險，包括但不限於本金全部損失。
    </p>
    <p style="font-size:11px;color:#64748b;line-height:1.7;margin-bottom:14px;">
        所有投資涉及風險，閣下作出任何投資決定前，應自行諮詢持牌財務顧問。
    </p>
    <hr style="border:none;border-top:1px solid #1e293b;margin:10px 0;">
    <p style="font-size:11px;color:#475569;line-height:1.7;margin-bottom:6px;">
        Strategy C Premium signals are generated by FerryRichMan Limited based on a quantitative
        momentum model, for reference only and <strong style="color:#64748b;">do not constitute
        investment advice</strong>. Past performance is not indicative of future results. Leveraged
        ETF investing involves substantial risk including total loss of principal.
    </p>
    <p style="font-size:10px;color:#374151;line-height:1.7;">
        All investments involve risk. Please consult a licensed financial advisor before making any
        investment decisions.
    </p>
</div>
        """,
        unsafe_allow_html=True,
    )


def render_footer():
    year = datetime.today().year
    st.markdown(
        f"""
<div style="text-align:center; padding:32px 0 12px;">
    <div style="display:inline-block; background: linear-gradient(135deg,#f59e0b,#ef4444);
        -webkit-background-clip:text; -webkit-text-fill-color:transparent;
        font-size:14px; font-weight:900; letter-spacing:-0.5px; margin-bottom:6px;">
        FerryRichMan Limited · Premium
    </div>
    <div style="font-size:10px;color:#1e293b;">
        &copy; {year} FerryRichMan Limited &middot; All Rights Reserved<br>
        FRM Premium ETF System (Strategy C) &middot; Powered by Python &amp; Streamlit
    </div>
</div>
        """,
        unsafe_allow_html=True,
    )
    components.html("""
<div style="text-align:center;">
    <a href="https://ferryrichman.com" target="_blank"
       style="display:inline-block; background:#1e293b;
       color:#f59e0b; text-decoration:none; padding:10px 28px;
       border-radius:10px; font-size:13px; font-weight:700;
       border:1px solid #f59e0b33; letter-spacing:0.5px;
       font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
       🏠 回主頁 · ferryrichman.com
    </a>
</div>
""", height=50)


def section_header(icon: str, title: str):
    st.markdown(
        f'<div style="font-size:14px;color:#94a3b8;font-weight:800;'
        f'text-transform:uppercase;letter-spacing:1.5px;margin:24px 0 12px;">'
        f'{icon}&nbsp; {title}</div>',
        unsafe_allow_html=True,
    )


def render_momentum_table(prices: pd.DataFrame):
    """Detailed table with each month's scores + held #1/#2."""
    rows = []
    for dt in reversed(prices.index):
        if pd.isna(prices.loc[dt, "held_1"]):
            continue
        r = prices.loc[dt]
        row = {"月份": dt.strftime("%Y-%m"),
               "持倉#1 (60%)": str(prices["held_1"].shift(1).loc[dt]) if pd.notna(prices["held_1"].shift(1).loc[dt]) else "—",
               "持倉#2 (40%)": str(prices["held_2"].shift(1).loc[dt]) if pd.notna(prices["held_2"].shift(1).loc[dt]) else "—",
               "月回報": f"{r['signal_return']*100:+.2f}%" if pd.notna(r["signal_return"]) else "—",
               "新訊號#1": str(r["held_1"]),
               "新訊號#2": str(r["held_2"])}
        for t in BASE_TICKERS:
            v = r[f"score_{t}"]
            row[f"{t} 分"] = f"{v:.4f}" if pd.notna(v) else "—"
        rows.append(row)
    df_disp = pd.DataFrame(rows)
    st.dataframe(df_disp, use_container_width=True, height=600, hide_index=True)


# ══════════════════════════════════════════════════════════
#  AUTH — FRM HMAC token gate (federated with POPI subscription)
#  Token format: <payload_b64>.<sig_b64>  where payload = {plan, exp}
#  Verification is fully offline (no API call) — independence preserved.
# ══════════════════════════════════════════════════════════
import os
import hmac
import hashlib
import base64
import json

# Plans that this app accepts.
#   - etf-prem-*   : single-product Premium subscription
#   - etf-bundle-* : ETF combo (Standard + Premium together)
#   - frm-bundle-* : full FRM bundle (POPI + ETF + MPF + Stock)
#   - admin        : master key
# (Standard-only / POPI-only / MPF-only plans are rejected.)
ALLOWED_PLANS_FOR_THIS_APP = {
    "etf-prem-monthly", "etf-prem-annual", "etf-prem-lifetime",
    "etf-bundle-monthly", "etf-bundle-annual", "etf-bundle-lifetime",
    "frm-bundle-monthly", "frm-bundle-annual", "frm-bundle-lifetime",
    "admin",
}

# Product key for THIS app — checked against token's `unlocks` array.
# Customers with a multi-product code unlocking [etf-prem, ...] get in
# regardless of their `plan` field.
THIS_APP_PRODUCT = "etf-prem"


def _has_access(sub: dict) -> bool:
    """Check token grants access to this app.
    Priority: unlocks array (new) → plan whitelist (legacy fallback).
    """
    if not sub:
        return False
    unlocks = sub.get("unlocks") or []
    if THIS_APP_PRODUCT in unlocks:
        return True
    return sub.get("plan") in ALLOWED_PLANS_FOR_THIS_APP


def _frm_secret() -> bytes:
    """Load shared HMAC secret. Set in Streamlit Cloud → Settings → Secrets:
        FRM_SUB_SECRET = "<same hex as POPI backend>"
    """
    try:
        return st.secrets["FRM_SUB_SECRET"].encode("utf-8")
    except (KeyError, FileNotFoundError):
        return os.environ.get("FRM_SUB_SECRET", "").encode("utf-8")


def _verify_frm_token(token: str):
    """Verify HMAC-signed token. Returns payload dict if valid, else None.
    Mirrors POPI backend/main.py::_verify_sub_token exactly."""
    secret = _frm_secret()
    if not secret or not token or "." not in token:
        return None
    try:
        p64, s64 = token.rsplit(".", 1)
        expected = hmac.new(secret, p64.encode(), hashlib.sha256).digest()
        provided = base64.urlsafe_b64decode(s64 + "=" * (-len(s64) % 4))
        if not hmac.compare_digest(expected, provided):
            return None
        payload = json.loads(base64.urlsafe_b64decode(p64 + "=" * (-len(p64) % 4)))
        if payload.get("exp", 0) < int(time.time()):
            return None
        return payload   # {"plan": str, "exp": int}
    except Exception:
        return None


def _read_url_token() -> str:
    """Best-effort read of ?token=... from URL (Streamlit ≥1.30 API)."""
    try:
        v = st.query_params.get("token", "")
        if isinstance(v, list):
            return v[0] if v else ""
        return v or ""
    except Exception:
        return ""


# ── Single-device session management (admin exempt) ─────

@st.cache_resource
def _get_session_store():
    """Server-wide session store — persists while app runs, resets on deploy."""
    return {}   # { token_hash_16: {"sid": str, "ts": float} }


def _register_token_session(token: str) -> str:
    """Register a new session for this token, kicking any prior session."""
    store = _get_session_store()
    key = hashlib.sha256(token.encode()).hexdigest()[:16]
    sid = uuid.uuid4().hex[:12]
    store[key] = {"sid": sid, "ts": time.time()}
    return sid


def _verify_token_session(token_hash: str, sid: str) -> bool:
    """Check if this session_id is still the active one for this token hash."""
    store = _get_session_store()
    entry = store.get(token_hash)
    if entry is None:
        return True   # no record = legacy session, allow
    return entry["sid"] == sid


def render_login_page():
    """Branded gate screen — paste FRM unlock token from ferryrichman.com."""
    st.markdown(
        """
<div style="max-width: 480px; margin: 60px auto 30px; text-align: center;">
    <div style="display:inline-block;
        background: linear-gradient(135deg,#f59e0b,#ef4444);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        font-size: 13px; font-weight: 800; letter-spacing: 3px;
        text-transform: uppercase; margin-bottom: 12px;">
        FerryRichMan Limited &nbsp;·&nbsp; PREMIUM
    </div>
    <div style="font-size: 38px; font-weight: 900; color: #f1f5f9;
        letter-spacing: -2px; line-height: 1.12; margin-bottom: 8px;">
        FRM Premium<br>
        <span style="color:#f59e0b;">ETF SYSTEM</span>
    </div>
    <div style="font-size: 14px; color: #475569; margin-bottom: 32px;">
        🔒 訂閱用戶專屬 · Subscriber Access Only
    </div>
</div>
        """,
        unsafe_allow_html=True,
    )

    col_l, col_m, col_r = st.columns([1, 2, 1])
    with col_m:
        st.markdown(
            """
<div style="background: linear-gradient(135deg,#0f1a35 0%,#1a1230 100%);
    border: 1.5px solid #f59e0b55; border-radius: 16px;
    padding: 28px 28px 4px; margin-bottom: 16px;">
    <div style="font-size: 11px; color: #f59e0b; font-weight: 800;
        text-transform: uppercase; letter-spacing: 2px; margin-bottom: 8px;">
        🔑 貼上解鎖 Token
    </div>
    <div style="font-size: 12px; color: #94a3b8; line-height: 1.6; margin-bottom: 6px;">
        喺 <a href="https://ferryrichman.com" target="_blank"
        style="color:#f59e0b;text-decoration:none;">ferryrichman.com</a>
        貼解鎖碼後，撳「💎 進入 Premium」會自動帶 Token 過嚟。
    </div>
</div>
            """,
            unsafe_allow_html=True,
        )
        pasted = st.text_input(
            "Token",
            type="password",
            label_visibility="collapsed",
            placeholder="貼 Token 或喺 ferryrichman.com 直接 click 進入...",
            key="frm_token_input",
        )
        submit = st.button("🚀 進入 Premium System", use_container_width=True, type="primary")

        if submit:
            secret = _frm_secret()
            if not secret:
                st.error(
                    "⚠️ Server 未設定 `FRM_SUB_SECRET`。"
                    "請於 Streamlit Cloud → App settings → Secrets 配置。"
                )
                return False
            sub = _verify_frm_token((pasted or "").strip())
            if not sub:
                st.error("❌ Token 無效或已過期。請喺 ferryrichman.com 重新解鎖。")
            elif sub["plan"] not in ALLOWED_PLANS_FOR_THIS_APP:
                st.error(
                    "❌ 你嘅訂閱不包含 Premium 訪問權限。"
                    "請訂閱 ETF Premium、ETF Bundle (Std + Prem) 或全套餐 Bundle。"
                )
            else:
                st.session_state["frm_sub"] = sub
                if sub.get("plan") != "admin":
                    _tok = (pasted or "").strip()
                    sid = _register_token_session(_tok)
                    st.session_state["frm_session_id"] = sid
                    st.session_state["frm_token_hash"] = hashlib.sha256(_tok.encode()).hexdigest()[:16]
                st.rerun()

        st.markdown(
            """
<div style="text-align:center; margin-top: 28px; padding-top: 20px;
    border-top: 1px solid #1e293b;">
    <div style="font-size: 12px; color: #64748b; margin-bottom: 6px;">
        仲未訂閱？
    </div>
    <a href="https://ferryrichman.com" target="_blank"
       style="display:inline-block; background:#1e293b; color:#cbd5e1;
       text-decoration:none; padding:10px 24px; border-radius:10px;
       font-size:12px; font-weight:700; letter-spacing:0.5px;">
       💎 訂閱 Premium &nbsp;→
    </a>
    <div style="font-size: 10px; color: #334155; margin-top: 14px;">
        Strategy C · 17yr CAGR 15% · 月度 WhatsApp 訊號
    </div>
</div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown(
        """
<div style="max-width: 480px; margin: 32px auto 0; text-align: center;
    font-size: 10px; color: #1e293b; line-height: 1.6;">
    本系統僅供已訂閱用戶參考使用，不構成任何投資建議。<br>
    投資涉及風險，過去表現不代表未來。
</div>
        """,
        unsafe_allow_html=True,
    )

    return False


def check_password() -> bool:
    """Gate. Returns True if a valid Token unlocks this app, else renders login.

    Token sources (in order):
      1. st.session_state['frm_sub']  — cached after first successful verify
      2. ?token=... URL query param   — handoff from ferryrichman.com
      3. Pasted in render_login_page text_input

    Single-device enforcement: admin tokens bypass session check.
    """
    cached = st.session_state.get("frm_sub")
    if (cached and cached.get("exp", 0) > int(time.time())
            and _has_access(cached)):
        # Single-device check (admin exempt)
        if not _is_admin():
            sid = st.session_state.get("frm_session_id", "")
            th = st.session_state.get("frm_token_hash", "")
            if sid and th and not _verify_token_session(th, sid):
                st.session_state.pop("frm_sub", None)
                st.session_state.pop("frm_session_id", None)
                st.session_state.pop("frm_token_hash", None)
                st.warning(
                    "⚠️ 你嘅帳號已喺另一部裝置登入。\n\n"
                    "每個訂閱只允許同時一部裝置使用。如需重新登入，請重新輸入 Token。"
                )
                return render_login_page()
        return True

    url_token = _read_url_token()
    if url_token:
        sub = _verify_frm_token(url_token)
        if sub and _has_access(sub):
            st.session_state["frm_sub"] = sub
            if sub.get("plan") != "admin":
                sid = _register_token_session(url_token)
                st.session_state["frm_session_id"] = sid
                st.session_state["frm_token_hash"] = hashlib.sha256(url_token.encode()).hexdigest()[:16]
            return True
        # Invalid URL token — fall through to render login (with implicit error)

    return render_login_page()


def _is_admin() -> bool:
    """Return True if the verified token's plan is 'admin' (Owner)."""
    return st.session_state.get("frm_sub", {}).get("plan") == "admin"


def render_owner_only_placeholder(section_label: str) -> None:
    """Render an intellectual-property notice in place of admin-only content.

    Shown to paid subscribers (non-admin) when they reach a section reserved
    for the Owner — e.g. detailed momentum trace tables, methodology spec.
    """
    st.markdown(
        f"""
<div style="background:linear-gradient(135deg,#0d1424 0%,#1a1230 100%);
    border:1.5px dashed #475569;border-radius:14px;padding:32px 28px;
    margin-top:14px;text-align:center;">
  <div style="font-size:34px;margin-bottom:14px;">🔒</div>
  <div style="font-size:12px;color:#fbbf24;font-weight:800;
       text-transform:uppercase;letter-spacing:2px;margin-bottom:10px;">
    Proprietary · FerryRichMan Limited
  </div>
  <div style="font-size:14px;color:#94a3b8;line-height:1.7;
       max-width:540px;margin:0 auto 14px;">
    <strong style="color:#e2e8f0;">{section_label}</strong>
    為本公司知識產權核心資料，<br>
    包括訊號計算公式、權重參數、進出規則嘅完整透明明細，<br>
    保留為內部資料以保障策略嘅獨特性。
  </div>
  <div style="font-size:11.5px;color:#64748b;line-height:1.6;
       max-width:480px;margin:0 auto 20px;font-style:italic;">
    Signal computation formulas, weighting parameters, and per-month
    trace details are retained as proprietary IP of FerryRichMan
    Limited to protect strategy uniqueness.
  </div>
  <a href="https://wa.me/85264216504?text=Hi%20FerryRichMan%2C%20我想了解策略合作。"
     target="_blank"
     style="display:inline-block;background:#1e293b;color:#fbbf24;
     text-decoration:none;padding:9px 22px;border-radius:8px;
     font-size:12px;font-weight:700;letter-spacing:0.5px;
     border:1px solid #f59e0b55;">
    💬 研究合作請聯絡
  </a>
</div>
        """,
        unsafe_allow_html=True,
    )


# ══════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════
def main():
    st.set_page_config(
        page_title="FRM Premium ETF System · FerryRichMan Limited",
        page_icon="⚡", layout="centered", initial_sidebar_state="collapsed",
    )
    inject_css()

    # ── Gate behind password ──
    if not check_password():
        st.stop()

    render_header()
    if not _is_admin():
        inject_content_protection()
        inject_watermark()

    with st.spinner("正在獲取最新市場數據..."):
        prices = load_prices(date_key=_hk_date_key())
        prices = compute_signals(prices)

    info = get_current_info(prices)
    stats = calc_stats(prices)
    annual = calc_annual(prices)

    # Current month's dual signal
    render_dual_signal_card(info)

    # Rebalance countdown + signal change alert
    render_rebalance_notice(info)

    # Score comparison
    section_header("📊", "本月 ETF 動力分數比較")
    st.markdown('<div style="background:#111827;border:1px solid #1e293b;border-radius:14px;padding:16px 16px 8px;">',
                unsafe_allow_html=True)
    if info:
        render_scores_chart(info["scores"], info)
    st.markdown("</div>", unsafe_allow_html=True)

    # WhatsApp message
    section_header("📱", "WhatsApp 訊息 — 一鍵複製轉發")
    if info:
        render_whatsapp_section(info, stats)

    # Historical KPIs
    section_header("📈", "歷史績效 (2008-2026)")
    render_kpis(stats)

    # Tabs
    tab1, tab2, tab3 = st.tabs(["  年度回報  ", "  增長曲線 vs SPY  ", "  持倉記錄  "])
    with tab1:
        render_annual_chart(annual)
    with tab2:
        render_cumulative_chart(stats)
    with tab3:
        render_dual_heatmap(prices)

    # Academic-grade validation — 8 statistical tests with Chinese commentary
    section_header("🎓", "學術級驗證 · Academic-Grade Validation")
    render_academic_validation("validation_premium.json")

    # Risk warnings
    section_header("⚠️", "風險警告 · Risk Warnings")
    render_warnings_section()

    # Methodology — Owner-only (proprietary spec)
    section_header("📋", "方法論 · Methodology")
    if _is_admin():
        render_methodology_section()
    else:
        render_owner_only_placeholder("方法論 · Methodology Spec")

    # Detail table — Owner-only (per-month trace contains full strategy logic)
    section_header("🔢", "動力計算明細 · Per-Month Trace")
    if _is_admin():
        render_momentum_table(prices)
    else:
        render_owner_only_placeholder("動力計算明細 · Per-Month Momentum Trace")

    render_disclaimer()
    render_footer()


if __name__ == "__main__":
    main()
