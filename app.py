from collections import defaultdict
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

DATA_PATH = "data/catchments.geojson"

ROUTE_CIRCLE: dict[str, str] = {
    "Red": "🔴", "Orange": "🟠", "Blue": "🔵",
    "Green-B": "🟢", "Green-C": "🟢", "Green-D": "🟢", "Green-E": "🟢",
    "Mattapan": "🔴",
}

RT_ROUTE_COLORS: dict[str, str] = {
    "Red":     "#DA291C",
    "Orange":  "#ED8B00",
    "Blue":    "#003DA5",
    "Green-B": "#00843D",
    "Green-C": "#00843D",
    "Green-D": "#00843D",
    "Green-E": "#00843D",
    "Mattapan":"#8B2000",
}

CR_COLOR = "#80276C"

RT_LEGEND      = {color: name.split("-")[0] for name, color in RT_ROUTE_COLORS.items()}
RT_COLOR_ORDER = list(dict.fromkeys(RT_ROUTE_COLORS.values()))

X_OPTIONS = {
    "Peak trips per hour":    "peak_trips_per_hr",
    "AM peak trips per hour": "tph_am_peak",
    "Midday trips per hour":  "tph_midday",
    "PM peak trips per hour": "tph_pm_peak",
}

Y_OPTIONS = {
    "Population and Jobs per acre (2024)": "pop_jobs_2024_per_acre",
    "Population per acre (2024)":          "pop_2024_per_acre",
    "Jobs per acre (2024)":                "jobs_2023_per_acre",
    "Population and Jobs per acre (2010)": "pop_jobs_2010_per_acre",
    "Population per acre (2010)":          "pop_2010_per_acre",
    "Jobs per acre (2010)":                "jobs_2011_per_acre",
}

NUMERIC_COLS = [
    "peak_trips_per_hr", "tph_am_peak", "tph_midday", "tph_pm_peak",
    "pop_2010", "pop_2024", "jobs_2011", "jobs_2023",
    "pop_2010_per_acre", "pop_2024_per_acre", "jobs_2011_per_acre", "jobs_2023_per_acre",
    "pop_jobs_2010_per_acre", "pop_jobs_2024_per_acre",
]


def _distinct_rt_colors(routes_str: str) -> list[str]:
    if pd.isna(routes_str):
        return ["#888888"]
    seen: set[str] = set()
    out: list[str] = []
    for r in routes_str.split(","):
        c = RT_ROUTE_COLORS.get(r)
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return out or ["#888888"]


BAR_HOVER = (
    '<span style="font-size:14px"><b>%{y}</b></span><br>'
    "<b>2010:</b> %{customdata[0]}<br>"
    "<b>2024:</b> %{customdata[1]}<br>"
    "<b>Change:</b> %{x:+d} population and jobs per acre"
    "<extra></extra>"
)


def _bar_hover(df: pd.DataFrame) -> np.ndarray:
    return np.stack([
        df["pop_jobs_2010_per_acre"].round(0).astype(int),
        df["pop_jobs_2024_per_acre"].round(0).astype(int),
    ], axis=1)


@st.cache_data
def load_data(mtime: float) -> pd.DataFrame:
    gdf = gpd.read_file(DATA_PATH)
    df = pd.DataFrame(gdf.drop(columns="geometry"))
    for col in NUMERIC_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def build_scatter(
    df_sub: pd.DataFrame,
    x_col: str, x_label: str,
    y_col: str, y_label: str,
    mode: str,
    df_fit: pd.DataFrame | None = None,
    jitter: bool = False,
) -> go.Figure:
    color_fn  = _distinct_rt_colors if mode == "Rapid Transit" else lambda _: [CR_COLOR]
    legend_map = RT_LEGEND if mode == "Rapid Transit" else {CR_COLOR: "Commuter Rail"}

    df_sub = df_sub.copy()
    df_sub["_colors"] = df_sub["routes"].apply(color_fn)
    valid = df_sub.dropna(subset=[x_col, y_col])

    # Axis ranges with padding
    x_min, x_max = valid[x_col].min(), valid[x_col].max()
    y_min, y_max = valid[y_col].min(), valid[y_col].max()
    x_pad = max(0.07 * (x_max - x_min), 0.5)
    y_pad = max(0.07 * (y_max - y_min), 0.5)
    x_range = [x_min - x_pad, x_max + x_pad]
    y_range = [y_min - y_pad, y_max + y_pad]

    fig = go.Figure()

    # OLS trendline — always fit on the full (unfiltered) dataset so the
    # baseline doesn't shift when downtown stations are toggled off.
    fit_source = (df_fit if df_fit is not None else df_sub).dropna(subset=[x_col, y_col])
    if len(fit_source) >= 2:
        coef = np.polyfit(fit_source[x_col], fit_source[y_col], 1)
        xl = np.linspace(x_range[0], x_range[1], 200)
        fig.add_trace(go.Scatter(
            x=xl, y=np.polyval(coef, xl),
            mode="lines",
            line=dict(color="rgba(0,0,0,0.2)", width=2, dash="dash"),
            hoverinfo="skip", showlegend=False,
        ))

    # Deterministic x jitter to spread stacked same-frequency stations
    if jitter:
        jitter_amt = max(0.008 * (x_max - x_min), 0.04)
        rng = np.random.default_rng(seed=abs(hash(tuple(valid.index.tolist()))) % (2**32))
        raw_jitter = rng.uniform(-jitter_amt, jitter_amt, size=len(valid))
        x_jitter = pd.Series(
            np.clip(valid[x_col].values + raw_jitter, 0, None) - valid[x_col].values,
            index=valid.index,
        )
    else:
        x_jitter = pd.Series(0.0, index=valid.index)

    # One trace per color; multi-line stations appear in each of their color's trace
    color_groups: dict[str, list] = defaultdict(list)
    for idx, colors in valid["_colors"].items():
        for c in colors:
            color_groups[c].append(idx)

    ordered_colors = [c for c in RT_COLOR_ORDER if c in color_groups]
    ordered_colors += sorted(c for c in color_groups if c not in RT_COLOR_ORDER)
    for color in ordered_colors:
        indices = color_groups[color]
        grp = valid.loc[indices]
        clists = grp["_colors"].tolist()
        name = legend_map.get(color, color)
        # Solid-color legend icon linked to the data trace via legendgroup
        fig.add_trace(go.Scatter(
            x=[None], y=[None], mode="markers",
            marker=dict(size=10, color=color),
            name=name, legendgroup=color, showlegend=True,
        ))
        fig.add_trace(go.Scatter(
            x=grp[x_col] + x_jitter.loc[grp.index],
            y=grp[y_col],
            mode="markers",
            name=name,
            legendgroup=color,
            marker=dict(
                size=16,
                color=[c[0] for c in clists],
                gradient=dict(
                    type=["horizontal" if len(c) > 1 else "none" for c in clists],
                    color=[c[1] if len(c) > 1 else c[0] for c in clists],
                ),
                line=dict(color="white", width=1),
            ),
            text=grp["stop_name"],
            customdata=np.stack([
                grp["route_names"].fillna(""),
                grp[x_col].round(1),
                grp[y_col].round(0).astype(int),
            ], axis=1),
            hovertemplate=(
                '<span style="font-size:14px"><b>%{text}</b></span><br>'
                "<b>Routes:</b> %{customdata[0]}<br>"
                f"<b>{x_label}:</b> %{{customdata[1]}}<br>"
                f"<b>{y_label}:</b> %{{customdata[2]}}"
                "<extra></extra>"
            ),
            showlegend=False,
        ))

    fig.update_layout(
        height=540,
        xaxis=dict(title=x_label, range=x_range),
        yaxis=dict(title=y_label, range=y_range),
        showlegend=mode == "Rapid Transit",
        legend=dict(orientation="v", title=""),
        margin=dict(l=60, r=140, t=15, b=50),
    )
    return fig


st.set_page_config(page_title="Densi-T", layout="wide")
st.markdown(
    "<style>.block-container{padding-top:1rem} .axis-label{text-align:right}</style>",
    unsafe_allow_html=True,
)
st.title("Densi-T")
st.caption("Transit service and neighborhood density across the MBTA network.")

df = load_data(Path(DATA_PATH).stat().st_mtime)

with st.sidebar:
    st.markdown("# Filters")
    st.markdown("**Mode**")
    mode_filter = st.segmented_control("Mode", ["Rapid Transit", "Commuter Rail"], default="Rapid Transit", label_visibility="collapsed")
    st.markdown("**Station area radius (mi)**")
    radius = st.select_slider("Station area radius (mi)", options=[0.25, 0.5, 1.0], value=1.0, label_visibility="collapsed")
    st.markdown("**Stations**")
    include_downtown = st.checkbox("Include Downtown and Back Bay Stations", value=True)

base_full = df[(df["buffer_mi"] == radius) & (df["mode"] == mode_filter)].copy()
base = base_full.copy()
if not include_downtown:
    base = base[~base["is_downtown_and_back_bay"]]

tab_scatter, tab_density = st.tabs(["Service vs. density", "Density change"])

with tab_scatter:
    xl, xs, yl, ys, _, jc = st.columns([0.7, 2, 0.7, 2, 0.3, 1.2], vertical_alignment="center")
    with xl:
        st.markdown('<p class="axis-label">X axis</p>', unsafe_allow_html=True)
    with xs:
        x_label = st.selectbox("X axis", list(X_OPTIONS.keys()), label_visibility="collapsed")
    with yl:
        st.markdown('<p class="axis-label">Y axis</p>', unsafe_allow_html=True)
    with ys:
        y_label = st.selectbox("Y axis", list(Y_OPTIONS.keys()), label_visibility="collapsed")
    with jc:
        jitter = st.checkbox("Jitter", value=True)

    x_col = X_OPTIONS[x_label]
    y_col = Y_OPTIONS[y_label]

    st.plotly_chart(
        build_scatter(base, x_col, x_label, y_col, y_label, mode_filter, df_fit=base_full, jitter=jitter),
        width="stretch",
    )

    # Residuals — fit on full dataset, evaluate on visible stations
    fit_valid = base_full.dropna(subset=[x_col, y_col])
    if len(fit_valid) >= 2:
        coef = np.polyfit(fit_valid[x_col], fit_valid[y_col], 1)
        res_df = base.dropna(subset=[x_col, y_col]).copy()
        predicted = np.polyval(coef, res_df[x_col])
        res_df["_residual"] = res_df[y_col] - predicted
        res_df["_pct"] = res_df["_residual"] / np.clip(predicted, 1e-6, None) * 100

        n_res = 10
        above = res_df.nlargest(n_res, "_residual")[["stop_name", "routes", "_residual", "_pct"]]
        below = res_df.nsmallest(n_res, "_residual")[["stop_name", "routes", "_residual", "_pct"]]

        def _to_circles(routes_str: str) -> str:
            if pd.isna(routes_str):
                return "🟣" if mode_filter == "Commuter Rail" else ""
            route_set = {r.strip() for r in routes_str.split(",")}
            seen: set[str] = set()
            out = []
            for r, circle in ROUTE_CIRCLE.items():
                if r in route_set and circle not in seen:
                    seen.add(circle)
                    out.append(circle)
            if any(r not in ROUTE_CIRCLE for r in route_set):
                out.append("🟣")
            return " ".join(out)

        def _fmt_residuals(sub: pd.DataFrame) -> pd.DataFrame:
            return (
                sub.reset_index(drop=True)
                .assign(routes=lambda d: d["routes"].map(_to_circles))
                .rename(columns={
                    "stop_name": "Station",
                    "routes": "Lines",
                    "_residual": "Density vs. expected (per acre)",
                    "_pct": "% vs. expected",
                })
                .assign(**{
                    "Density vs. expected (per acre)": lambda d: d["Density vs. expected (per acre)"].map(lambda v: f"{v:+.0f}"),
                    "% vs. expected": lambda d: d["% vs. expected"].map(lambda v: f"{v:+.0f}%"),
                })
            )

        col_above, col_below = st.columns(2)
        with col_above:
            st.markdown("**Well-developed / Under-served** (above the line)")
            st.dataframe(_fmt_residuals(above), hide_index=True, use_container_width=True, column_config={"Lines": st.column_config.TextColumn(width="small")})
        with col_below:
            st.markdown("**Less-developed / Over-served** (below the line)")
            st.dataframe(_fmt_residuals(below), hide_index=True, use_container_width=True, column_config={"Lines": st.column_config.TextColumn(width="small")})

with tab_density:
    st.subheader("Population and jobs density change, 2010–2024")

    base["density_change"] = base["pop_jobs_2024_per_acre"] - base["pop_jobs_2010_per_acre"]

    n = st.slider("Stations to show", 5, 30, 15)
    col_gain, col_loss = st.columns(2)

    gainers = base.nlargest(n, "density_change").sort_values("density_change")
    losers  = base.nsmallest(n, "density_change").sort_values("density_change", ascending=False)

    def _bar_label(row) -> str:
        if mode_filter != "Rapid Transit":
            return row["stop_name"]
        circles = _to_circles(row["routes"])
        return f"{circles} {row['stop_name']}" if circles else row["stop_name"]

    bar_color = CR_COLOR if mode_filter == "Commuter Rail" else "#555555"

    def _make_bar(df: pd.DataFrame) -> go.Figure:
        return go.Figure(go.Bar(
            x=df["density_change"].round(0).astype(int),
            y=df.apply(_bar_label, axis=1),
            orientation="h",
            marker_color=bar_color,
            customdata=_bar_hover(df),
            hovertemplate=BAR_HOVER,
            showlegend=False,
        ))

    with col_gain:
        st.caption("Most growth")
        fig_gain = _make_bar(gainers)
        fig_gain.update_layout(height=max(350, n * 24), margin=dict(t=10))
        st.plotly_chart(fig_gain, width="stretch")

    with col_loss:
        st.caption("Least growth / most decline")
        fig_loss = _make_bar(losers)
        fig_loss.update_layout(height=max(350, n * 24), margin=dict(t=10))
        st.plotly_chart(fig_loss, width="stretch")
