"""Page 1 — 広告一覧 (searchable, filterable ad browser)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from db import get_ads, get_conn

_PREVIEW_LEN = 80


st.title("📋 広告一覧")

with get_conn() as conn:
    ads = get_ads(conn)

if not ads:
    st.warning("データがありません。")
    st.stop()

df = pd.DataFrame(ads)
df["recorded_at"] = pd.to_datetime(df["recorded_at"], errors="coerce")
df["duration_sec"] = df["duration_sec"].fillna(0).round(1)
df["full_text"] = df["full_text"].fillna("")
df["language"] = df["language"].fillna("—")
df["speaker_count"] = df["speaker_count"].fillna(0).astype(int)

# ── Filters ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("フィルタ")
    search = st.text_input("テキスト検索（書き起こし）", placeholder="プレミアム")
    langs = ["全て", *sorted(df["language"].unique().tolist())]
    lang_sel = st.selectbox("言語", langs)
    spk_min, spk_max = int(df["speaker_count"].min()), int(df["speaker_count"].max())
    spk_range = st.slider(
        "話者数", spk_min, max(spk_max, 1), (spk_min, max(spk_max, 1))
    )
    dur_min, dur_max = float(df["duration_sec"].min()), float(df["duration_sec"].max())
    dur_range = st.slider(
        "尺（秒）",
        dur_min,
        max(dur_max, 1.0),
        (dur_min, max(dur_max, 1.0)),
    )

filtered = df.copy()
if search:
    filtered = filtered[filtered["full_text"].str.contains(search, na=False)]
if lang_sel != "全て":
    filtered = filtered[filtered["language"] == lang_sel]
filtered = filtered[
    (filtered["speaker_count"] >= spk_range[0])
    & (filtered["speaker_count"] <= spk_range[1])
    & (filtered["duration_sec"] >= dur_range[0])
    & (filtered["duration_sec"] <= dur_range[1])
]

st.caption(f"{len(filtered)} 件 / {len(df)} 件")

# ── Table ─────────────────────────────────────────────────────────────────────
display = filtered[
    [
        "id",
        "filename",
        "recorded_at",
        "language",
        "speaker_count",
        "duration_sec",
        "full_text",
    ]
].copy()
display.columns = [
    "ID",
    "ファイル名",
    "録音日時",
    "言語",
    "話者数",
    "尺(秒)",
    "書き起こし（抜粋）",
]
display["書き起こし（抜粋）"] = display["書き起こし（抜粋）"].apply(
    lambda t: (t[:_PREVIEW_LEN] + "…") if len(t) > _PREVIEW_LEN else t
)

selected = st.dataframe(
    display,
    use_container_width=True,
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
)

# ── Navigate to detail ────────────────────────────────────────────────────────
rows = selected.get("selection", {}).get("rows", [])
if rows:
    idx = rows[0]
    ad_id = int(display.iloc[idx]["ID"])
    st.session_state["selected_ad_id"] = ad_id
    st.success(f"ad_id={ad_id} を選択しました → 「広告詳細」ページで確認できます")
