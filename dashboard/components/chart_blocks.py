"""
Plotly chart builders — dark theme, all return go.Figure for st.plotly_chart().
"""

import copy
import pandas as pd
import plotly.graph_objects as go

_PAPER_BG = "#070C14"
_PLOT_BG  = "#0A1220"
_GRID     = "#0F1E2E"
_TICK     = "#1A2A3A"
_FONT_CLR = "#556677"
_HOVER_BG = "#0D1828"

_LAYOUT_BASE = dict(
    paper_bgcolor=_PAPER_BG,
    plot_bgcolor=_PLOT_BG,
    font=dict(color=_FONT_CLR, family="sans-serif", size=11),
    margin=dict(l=48, r=16, t=36, b=40),
    hovermode="x unified",
    hoverlabel=dict(bgcolor=_HOVER_BG, bordercolor=_TICK, font=dict(color="#AABBCC", size=11)),
    legend=dict(
        bgcolor=_PAPER_BG, bordercolor=_TICK, borderwidth=1,
        orientation="h", x=0, y=-0.18, font=dict(color="#778899"),
    ),
    xaxis=dict(
        gridcolor=_GRID, showgrid=True, tickcolor=_TICK, linecolor=_TICK,
        tickfont=dict(color=_FONT_CLR), title_font=dict(color=_FONT_CLR),
    ),
    yaxis=dict(
        gridcolor=_GRID, showgrid=True, tickcolor=_TICK, linecolor=_TICK,
        zeroline=False, tickfont=dict(color=_FONT_CLR), title_font=dict(color=_FONT_CLR),
    ),
)


def _base_layout(**overrides) -> dict:
    layout = copy.deepcopy(_LAYOUT_BASE)
    layout.update(overrides)
    return layout


def _threshold_line(fig, y: float, label: str, color: str = "#334455") -> None:
    fig.add_hline(
        y=y, line_dash="dot", line_color=color, line_width=1,
        annotation_text=label,
        annotation_font=dict(color=color, size=10),
        annotation_position="top right",
    )


def room_scores_chart(df: pd.DataFrame) -> go.Figure:
    t   = df["timestamp"]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=t, y=df["room_readiness"], name="Room Readiness",
        mode="lines", line=dict(color="#3DFF8A", width=2),
        fill="tozeroy", fillcolor="rgba(61,255,138,0.04)",
        hovertemplate="%{y}<extra>Readiness</extra>"))
    fig.add_trace(go.Scatter(x=t, y=df["recovery_score"], name="Recovery",
        mode="lines", line=dict(color="#66CCFF", width=2),
        hovertemplate="%{y}<extra>Recovery</extra>"))
    fig.add_trace(go.Scatter(x=t, y=df["air_strain"], name="Air Strain",
        mode="lines", line=dict(color="#FF8844", width=2),
        hovertemplate="%{y}<extra>Air Strain</extra>"))
    _threshold_line(fig, 75, "Good ≥ 75", color="#1E4A2A")
    fig.update_layout(**_base_layout(
        title=dict(text="Room Performance Over Time", font=dict(color="#3A5A7A", size=13)),
        yaxis=dict(range=[0, 100], gridcolor=_GRID, showgrid=True, tickcolor=_TICK,
                   linecolor=_TICK, zeroline=False, title="Score (0–100)",
                   tickfont=dict(color=_FONT_CLR), title_font=dict(color=_FONT_CLR)),
    ))
    return fig


def temperature_chart(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_hrect(y0=18, y1=26, fillcolor="rgba(0,255,180,0.04)", line_width=0,
                  annotation_text="Comfort zone", annotation_font=dict(color="#1A4A3A", size=10),
                  annotation_position="top right")
    fig.add_trace(go.Scatter(x=df["timestamp"], y=df["indoor_temp"], name="Temperature",
        mode="lines", line=dict(color="#00FFCC", width=2),
        hovertemplate="%{y:.1f} °C<extra></extra>"))
    fig.update_layout(**_base_layout(
        title=dict(text="Temperature", font=dict(color="#3A5A7A", size=13)),
        yaxis=dict(title="°C", gridcolor=_GRID, showgrid=True, tickcolor=_TICK,
                   linecolor=_TICK, zeroline=False,
                   tickfont=dict(color=_FONT_CLR), title_font=dict(color=_FONT_CLR)),
    ))
    return fig


def humidity_chart(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    _threshold_line(fig, 40, "Dry below 40 %", color="#4A3200")
    _threshold_line(fig, 65, "High above 65 %", color="#004A2A")
    fig.add_trace(go.Scatter(x=df["timestamp"], y=df["indoor_humidity"], name="Humidity",
        mode="lines", line=dict(color="#66CCFF", width=2),
        fill="tozeroy", fillcolor="rgba(102,204,255,0.04)",
        hovertemplate="%{y:.0f} %<extra></extra>"))
    fig.update_layout(**_base_layout(
        title=dict(text="Humidity", font=dict(color="#3A5A7A", size=13)),
        yaxis=dict(title="%", range=[0, 100], gridcolor=_GRID, showgrid=True,
                   tickcolor=_TICK, linecolor=_TICK, zeroline=False,
                   tickfont=dict(color=_FONT_CLR), title_font=dict(color=_FONT_CLR)),
    ))
    return fig


def tvoc_chart(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    _threshold_line(fig, 100, "Moderate ≥ 100", color="#444400")
    _threshold_line(fig, 150, "Poor ≥ 150",     color="#4A2200")
    fig.add_trace(go.Scatter(x=df["timestamp"], y=df["air_quality"], name="TVOC",
        mode="lines", line=dict(color="#FFCC00", width=2),
        hovertemplate="%{y:.0f} ppb<extra></extra>"))
    fig.update_layout(**_base_layout(
        title=dict(text="Air Quality (TVOC)", font=dict(color="#3A5A7A", size=13)),
        yaxis=dict(title="ppb", gridcolor=_GRID, showgrid=True, tickcolor=_TICK,
                   linecolor=_TICK, zeroline=False,
                   tickfont=dict(color=_FONT_CLR), title_font=dict(color=_FONT_CLR)),
    ))
    return fig


def eco2_chart(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    _threshold_line(fig, 1000, "Elevated ≥ 1000 ppm", color="#3A2A00")
    fig.add_trace(go.Scatter(x=df["timestamp"], y=df["indoor_eco2"], name="eCO₂",
        mode="lines", line=dict(color="#FFCC99", width=2),
        hovertemplate="%{y:.0f} ppm<extra></extra>"))
    fig.update_layout(**_base_layout(
        title=dict(text="eCO₂", font=dict(color="#3A5A7A", size=13)),
        yaxis=dict(title="ppm", gridcolor=_GRID, showgrid=True, tickcolor=_TICK,
                   linecolor=_TICK, zeroline=False,
                   tickfont=dict(color=_FONT_CLR), title_font=dict(color=_FONT_CLR)),
    ))
    return fig


def motion_chart(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["timestamp"], y=df["motion"].astype(int), name="Motion",
        mode="lines", line=dict(color="#DDDD00", width=0, shape="hv"),
        fill="tozeroy", fillcolor="rgba(200,180,0,0.18)",
        hovertemplate="%{customdata}<extra></extra>",
        customdata=["Detected" if v else "None" for v in df["motion"]],
    ))
    fig.update_layout(**_base_layout(
        title=dict(text="Room Activity (Motion)", font=dict(color="#3A5A7A", size=13)),
        yaxis=dict(
            tickvals=[0, 1], ticktext=["None", "Detected"], range=[-0.1, 1.4],
            gridcolor=_GRID, showgrid=False, tickcolor=_TICK, linecolor=_TICK, zeroline=False,
            tickfont=dict(color=_FONT_CLR), title_font=dict(color=_FONT_CLR),
        ),
        legend=dict(bgcolor=_PAPER_BG, bordercolor=_TICK, borderwidth=1,
                    orientation="h", x=0, y=-0.25, font=dict(color="#778899")),
    ))
    return fig
