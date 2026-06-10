"""Annual Sports Game Price Forecaster — Streamlit app.

Tracks price depreciation of annual Xbox sports franchises (Madden NFL, NBA 2K)
using PC digital-store prices as a free proxy, fits a depreciation curve from
past editions, and forecasts when the current edition hits key price points.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.config import FRANCHISES, PRICE_THRESHOLDS
from src import data_sources as ds
from src import model as m

st.set_page_config(
    page_title="Annual Sports Game Price Forecaster",
    page_icon="🎮",
    layout="wide",
)


# --------------------------------------------------------------------------- #
# Data loading (cached so we don't hammer the APIs on every interaction)
# --------------------------------------------------------------------------- #

def _api_key() -> str:
    return str(st.secrets.get("ITAD_API_KEY", "")).strip()


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def load_history(search_term: str, release_iso: str, api_key: str):
    """Daily-low price history for one edition; None if not sold on PC."""
    release = date.fromisoformat(release_iso)
    game_id = ds.itad_find_game_id(search_term, api_key)
    if not game_id:
        return None
    return ds.itad_price_history(game_id, release, api_key)


@st.cache_data(ttl=3 * 3600, show_spinner=False)
def load_current_price(search_term: str):
    return ds.cheapshark_current_price(search_term)


# --------------------------------------------------------------------------- #
# Header
# --------------------------------------------------------------------------- #

st.title("🎮 Annual Sports Game Price Forecaster")
st.caption(
    "Forecasting price depreciation for annual sports franchises, using past "
    "editions to predict the current one."
)

api_key = _api_key()
if not api_key or api_key.startswith("paste-"):
    st.error(
        "No IsThereAnyDeal API key found. Add it to `.streamlit/secrets.toml` "
        "(locally) or the app's **Secrets** box (on Streamlit Cloud)."
    )
    st.stop()

st.info(
    "📌 **About the prices:** Xbox console prices have no free public API, so "
    "this app uses **PC digital-store prices** (Steam, Epic, etc.) as a proxy. "
    "The *shape* of the depreciation curve closely tracks the Xbox version. "
    "History comes from IsThereAnyDeal; the current price from CheapShark."
)

franchise_key = st.selectbox(
    "Choose a franchise",
    options=list(FRANCHISES.keys()),
    format_func=lambda k: FRANCHISES[k].name,
)
franchise = FRANCHISES[franchise_key]
current = franchise.current_edition


# --------------------------------------------------------------------------- #
# Load data
# --------------------------------------------------------------------------- #

with st.spinner("Fetching price history…"):
    histories: dict[str, list] = {}
    missing: list[str] = []
    for ed in franchise.editions:
        if ed.is_projected:
            continue  # unreleased — forecast only, no data to fetch
        pts = load_history(ed.search_term, ed.release_date.isoformat(), api_key)
        if pts:
            histories[ed.title] = pts
        else:
            missing.append(ed.title)

# Pool the cumulative-min envelopes of PAST editions to fit the curve.
pooled = []
for ed in franchise.past_editions:
    if ed.title in histories:
        pooled.extend(m.to_cumulative_min(histories[ed.title]))

if len(pooled) < 4:
    st.warning(
        "Not enough past-edition price history on PC to fit a model for this "
        "franchise yet."
    )
    st.stop()

params = m.fit_curve(pooled, franchise.msrp)

if missing:
    st.caption(f"ℹ️ Not available on PC (excluded): {', '.join(missing)}")


# --------------------------------------------------------------------------- #
# Section 1 — Historical price curves (one line per edition)
# --------------------------------------------------------------------------- #

st.header("1 · Historical depreciation by edition")
st.caption(
    "Each line is the **lowest price available by that day** since release. "
    "The dashed black line is the fitted depreciation model."
)

fig1 = go.Figure()
for title, pts in histories.items():
    cm = m.to_cumulative_min(pts)
    is_current = title == current.title
    fig1.add_trace(
        go.Scatter(
            x=[p.days_since_release for p in cm],
            y=[p.price for p in cm],
            mode="lines",
            name=title + (" (current)" if is_current else ""),
            line=dict(width=3 if is_current else 2, dash="solid"),
        )
    )

# Fitted model curve.
fit_x, fit_y = m.curve_line(params, max_days=420)
fig1.add_trace(
    go.Scatter(x=fit_x, y=fit_y, mode="lines", name="Fitted model",
               line=dict(color="black", width=2, dash="dash"))
)
for thr in PRICE_THRESHOLDS:
    fig1.add_hline(y=thr, line=dict(color="gray", width=1, dash="dot"),
                   annotation_text=f"${thr}", annotation_position="right")
fig1.update_layout(
    xaxis_title="Days since release",
    yaxis_title="Lowest price (USD)",
    height=480,
    legend=dict(orientation="h", yanchor="bottom", y=1.02),
)
st.plotly_chart(fig1, use_container_width=True)


# --------------------------------------------------------------------------- #
# Section 2 — Current edition: actual vs. predicted
# --------------------------------------------------------------------------- #

st.header(f"2 · {current.title} — actual vs. forecast")

current_pts = histories.get(current.title, [])
current_cm = m.to_cumulative_min(current_pts) if current_pts else []
days_so_far = current_cm[-1].days_since_release if current_cm else 0

# Current cheapest price (CheapShark) shown as a headline metric.
cp = load_current_price(current.search_term)
col_a, col_b, col_c = st.columns(3)
col_a.metric("Days since release", f"{(date.today() - current.release_date).days}")
if cp:
    col_b.metric("Cheapest now (PC)", f"${cp.price:.2f}", help=f"via {cp.store} (CheapShark)")
else:
    col_b.metric("Cheapest now (PC)", "—")
col_c.metric("Modeled price floor", f"${params.floor:.2f}")

# How far to extend the forecast line: cover the data, the lowest threshold, and a buffer.
target_day = params.days_to_price(min(PRICE_THRESHOLDS))
max_days = int(max(days_so_far, target_day or 0, 365)) + 45
pred_x, pred_y = m.curve_line(params, max_days=max_days)

fig2 = go.Figure()
if current_cm:
    fig2.add_trace(go.Scatter(
        x=[p.days_since_release for p in current_cm],
        y=[p.price for p in current_cm],
        mode="lines+markers", name="Actual (lowest to date)",
        line=dict(color="#1f77b4", width=3),
    ))
fig2.add_trace(go.Scatter(
    x=pred_x, y=pred_y, mode="lines", name="Predicted trajectory",
    line=dict(color="#d62728", width=2, dash="dash"),
))
for thr in PRICE_THRESHOLDS:
    fig2.add_hline(y=thr, line=dict(color="gray", width=1, dash="dot"),
                   annotation_text=f"${thr}", annotation_position="right")
fig2.update_layout(
    xaxis_title="Days since release",
    yaxis_title="Price (USD)",
    height=460,
    legend=dict(orientation="h", yanchor="bottom", y=1.02),
)
st.plotly_chart(fig2, use_container_width=True)


# --------------------------------------------------------------------------- #
# Section 3 — Forecast table
# --------------------------------------------------------------------------- #

st.header("3 · Forecast: when does it hit each price?")
st.caption(
    f"For the live edition ({current.title}). Once an edition is fully "
    "depreciated these are all *actual* dates — see **Section 4** for the "
    "forward-looking projection of the upcoming edition."
)

rows = []
for thr in PRICE_THRESHOLDS:
    actual_day = m.first_crossing_day(current_pts, thr) if current_pts else None
    model_day = params.days_to_price(thr)

    if actual_day is not None:
        when = current.release_date + timedelta(days=actual_day)
        status = "✅ Already reached"
        basis = "Actual"
    elif model_day is None:
        when = None
        status = "🚫 Not expected (below modeled floor)"
        basis = "Model"
    else:
        when = current.release_date + timedelta(days=int(round(model_day)))
        status = "📈 Forecast" if when >= date.today() else "📈 Forecast (overdue)"
        basis = "Model"

    rows.append({
        "Price target": f"${thr:.2f}",
        "Expected date": when.strftime("%b %d, %Y") if when else "—",
        "Days from release": "—" if when is None
            else str((when - current.release_date).days),
        "Basis": basis,
        "Status": status,
    })

st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


# --------------------------------------------------------------------------- #
# Section 4 — Next edition projection (keeps the tool forward-looking)
# --------------------------------------------------------------------------- #

nxt = franchise.next_edition
if nxt is not None:
    st.header(f"4 · Projection for {nxt.title} — upcoming, not yet released")
    st.warning(
        f"🔮 **Model projection only.** Anchored on an **estimated** release of "
        f"**{nxt.release_date.strftime('%B %d, %Y')}**. {nxt.title} hasn't "
        "launched, so there is no actual price data yet — every value below is "
        f"the fitted {franchise.name} depreciation curve applied to that date."
    )

    proj_rows = []
    for thr in PRICE_THRESHOLDS:
        model_day = params.days_to_price(thr)
        if model_day is None:
            proj_rows.append({
                "Price target": f"${thr:.2f}",
                "Projected date": "—",
                "Days after release": "—",
                "Basis": "🔮 Projection (below modeled floor)",
            })
        else:
            d = int(round(model_day))
            when = nxt.release_date + timedelta(days=d)
            proj_rows.append({
                "Price target": f"${thr:.2f}",
                "Projected date": when.strftime("%b %d, %Y"),
                "Days after release": str(d),
                "Basis": "🔮 Projection",
            })
    st.dataframe(pd.DataFrame(proj_rows), hide_index=True, use_container_width=True)

    # Projected price trajectory on a calendar axis.
    target_day_n = params.days_to_price(min(PRICE_THRESHOLDS))
    span = max(int(target_day_n or 0) + 60, 365)
    xs = list(range(0, span + 1, 5))
    proj_dates = [nxt.release_date + timedelta(days=d) for d in xs]
    proj_prices = [round(params.price_at(d), 2) for d in xs]

    fig4 = go.Figure()
    fig4.add_trace(go.Scatter(
        x=proj_dates, y=proj_prices, mode="lines", name="Projected price",
        line=dict(color="#9467bd", width=3, dash="dash"),
    ))
    for thr in PRICE_THRESHOLDS:
        fig4.add_hline(y=thr, line=dict(color="gray", width=1, dash="dot"),
                       annotation_text=f"${thr}", annotation_position="right")
    fig4.update_layout(
        xaxis_title="Projected calendar date",
        yaxis_title="Projected price (USD)",
        height=440,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    st.plotly_chart(fig4, use_container_width=True)


with st.expander("How the model works"):
    st.markdown(
        f"""
- **Data:** lowest PC price by day for each past edition of {franchise.name},
  pulled from IsThereAnyDeal.
- **Curve:** an exponential decay toward a floor,
  `price(t) = floor + (p0 − floor)·e^(−k·t)`, fit to the pooled past editions.
- **This franchise's fit:** floor **${params.floor:.2f}**, launch
  **${params.p0:.2f}**, decay **{params.k:.4f}/day**, from
  **{params.n_points}** data points.
- **Forecast:** the fitted curve is applied to {current.title}. Where the
  current edition's *actual* price has already crossed a threshold, the table
  shows that real date instead of the model's estimate.
"""
    )

st.caption(
    "Prices are PC digital-store proxies in USD. Educational use only — not "
    "purchasing or financial advice."
)
