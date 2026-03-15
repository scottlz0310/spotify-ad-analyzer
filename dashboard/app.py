"""Spotify Ad Analyzer — Dashboard entry point (overview page)."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from db import DB_PATH, get_ads, get_conn

st.set_page_config(
    page_title="Spotify Ad Analyzer",
    page_icon="🎵",
    layout="wide",
)

st.title("🎵 Spotify Ad Analyzer")
st.caption("録音広告の書き起こし・話者分類・音声類似度 ダッシュボード")

if not DB_PATH.exists():
    st.error(
        f"データベースが見つかりません: `{DB_PATH}`\n"
        "analyzer を起動して広告を処理してください。"
    )
    st.stop()

with get_conn() as conn:
    ads = get_ads(conn)

if not ads:
    st.warning(
        "まだ広告データがありません。analyzer を起動して録音を処理してください。"
    )
    st.stop()

total = len(ads)
with_transcript = sum(1 for a in ads if a["full_text"])
languages = {a["language"] for a in ads if a["language"]}
avg_dur = sum(a["duration_sec"] or 0 for a in ads) / total if total else 0

# ── KPI ──────────────────────────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)
c1.metric("総広告数", total)
c2.metric("書き起こし済み", with_transcript)
c3.metric("検出言語", "・".join(sorted(languages)) or "—")
c4.metric("平均尺", f"{avg_dur:.1f}s")

st.divider()

# ── Recent ads ────────────────────────────────────────────────────────────────
st.subheader("最近の広告（直近 10 件）")

import pandas as pd  # noqa: E402

_PREVIEW_LEN = 60

recent = ads[-10:][::-1]
df = pd.DataFrame(recent)[
    ["id", "filename", "language", "speaker_count", "duration_sec", "full_text"]
]
df.columns = ["ID", "ファイル名", "言語", "話者数", "尺(秒)", "書き起こし（抜粋）"]
df["書き起こし（抜粋）"] = df["書き起こし（抜粋）"].apply(
    lambda t: (t[:_PREVIEW_LEN] + "…") if len(t) > _PREVIEW_LEN else t
)
df["尺(秒)"] = df["尺(秒)"].fillna(0).round(1)

st.dataframe(df, use_container_width=True, hide_index=True)

st.divider()
st.info("👈 左サイドバーからページを選択してください")

# ── WAV folder status ─────────────────────────────────────────────────────────
shared = Path("/app/shared")
if shared.exists():
    wavs = list(shared.glob("spotify_ad_*.wav"))
    st.caption(f"📁 shared/ に WAV ファイル {len(wavs)} 件")
else:
    st.caption("📁 shared/ ディレクトリが見つかりません")
