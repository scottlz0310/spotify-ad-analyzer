"""Page 2 — 広告詳細 (transcript, speaker timeline, WAV playback)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from db import get_ads, get_conn, get_llm, get_segments, get_transcript

st.set_page_config(page_title="広告詳細", page_icon="🔍", layout="wide")
st.title("🔍 広告詳細")

conn = get_conn()
ads = get_ads(conn)

if not ads:
    st.warning("データがありません。")
    conn.close()
    st.stop()

# ── Ad selector ───────────────────────────────────────────────────────────────
ad_options = {a["id"]: f"[{a['id']}] {a['filename']}" for a in ads}
default_id = st.session_state.get("selected_ad_id", ads[0]["id"])
if default_id not in ad_options:
    default_id = ads[0]["id"]

ad_id = st.selectbox(
    "広告を選択",
    options=list(ad_options.keys()),
    format_func=lambda x: ad_options[x],
    index=list(ad_options.keys()).index(default_id),
)

ad_info = next((a for a in ads if a["id"] == ad_id), None)
transcript = get_transcript(conn, ad_id)
segments = get_segments(conn, ad_id)
llm = get_llm(conn, ad_id)
conn.close()

if not ad_info:
    st.error("広告が見つかりません。")
    st.stop()

# ── Header ────────────────────────────────────────────────────────────────────
st.subheader(ad_info["filename"])
c1, c2, c3, c4 = st.columns(4)
c1.metric("言語", ad_info.get("language") or "—")
c2.metric("話者数", ad_info.get("speaker_count") or 0)
c3.metric("尺", f"{ad_info.get('duration_sec') or 0:.1f}s")
c4.metric("Whisperモデル", ad_info.get("whisper_model") or "—")

# ── WAV playback ──────────────────────────────────────────────────────────────
shared = Path("/app/shared")
wav_path = shared / ad_info["filename"]
if wav_path.exists():
    st.audio(str(wav_path))
else:
    st.caption(f"🔇 WAV ファイルなし（`{wav_path}`）")

st.divider()

# ── Transcript ────────────────────────────────────────────────────────────────
st.subheader("📝 全文書き起こし")
if transcript and transcript.get("full_text"):
    st.write(transcript["full_text"])
else:
    st.caption("書き起こしデータなし")

# ── Speaker timeline ──────────────────────────────────────────────────────────
st.subheader("🗣️ 話者タイムライン")
if segments:
    seg_df = pd.DataFrame(segments)
    speakers = sorted(seg_df["speaker"].unique())
    color_map = {
        spk: px.colors.qualitative.Plotly[i % len(px.colors.qualitative.Plotly)]
        for i, spk in enumerate(speakers)
    }
    base = pd.Timestamp("2000-01-01")
    seg_df["start_dt"] = seg_df["start_sec"].apply(
        lambda s: base + pd.Timedelta(seconds=float(s))
    )
    seg_df["end_dt"] = seg_df["end_sec"].apply(
        lambda s: base + pd.Timedelta(seconds=float(s))
    )
    fig = px.timeline(
        seg_df,
        x_start="start_dt",
        x_end="end_dt",
        y="speaker",
        color="speaker",
        text="text",
        color_discrete_map=color_map,
        hover_data={"text": True, "start_sec": True, "end_sec": True},
    )
    fig.update_layout(
        xaxis_title="時間",
        yaxis_title="",
        showlegend=True,
        height=max(180, len(speakers) * 80 + 60),
        margin={"l": 0, "r": 0, "t": 10, "b": 0},
    )
    fig.update_xaxes(tickformat="%M:%S")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.caption("セグメントデータなし")

# ── Segment table ─────────────────────────────────────────────────────────────
if segments:
    st.subheader("📊 セグメント一覧")
    seg_df = pd.DataFrame(segments)[["speaker", "start_sec", "end_sec", "text"]]
    seg_df.columns = ["話者", "開始(秒)", "終了(秒)", "テキスト"]
    seg_df["開始(秒)"] = seg_df["開始(秒)"].round(1)
    seg_df["終了(秒)"] = seg_df["終了(秒)"].round(1)
    st.dataframe(seg_df, use_container_width=True, hide_index=True)

# ── LLM analysis ──────────────────────────────────────────────────────────────
st.divider()
st.subheader("🤖 LLM 解析")
if llm:
    c1, c2, c3 = st.columns(3)
    c1.metric("商品名", llm.get("product_name") or "—")
    c2.metric("広告種別", llm.get("ad_type") or "—")
    c3.metric("トーン", llm.get("tone") or "—")
    if llm.get("summary"):
        st.write("**概要:** " + llm["summary"])
else:
    st.caption("LLM 解析なし（Ollama が未設定、または未処理）")
