"""Page 3 — 話者類似度 (voice embedding cosine similarity)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from db import get_ads, get_all_embeddings, get_conn

st.set_page_config(page_title="話者類似度", page_icon="🔊", layout="wide")
st.title("🔊 話者類似度")
st.caption("音声埋め込みベクトルのコサイン類似度で同一話者・同一CMを検索します")


def cosine(a: list[float], b: list[float]) -> float:
    va = np.array(a, dtype=np.float32)
    vb = np.array(b, dtype=np.float32)
    denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
    return float(np.dot(va, vb) / denom) if denom > 0 else 0.0


conn = get_conn()
ads = get_ads(conn)
embeddings = get_all_embeddings(conn)
conn.close()

if not ads or not embeddings:
    st.warning("データがありません。")
    st.stop()

ad_map = {a["id"]: a for a in ads}
ids_with_emb = sorted(embeddings.keys())

# ── Mode selector ─────────────────────────────────────────────────────────────
mode = st.radio(
    "表示モード",
    ["特定広告との類似度ランキング", "全広告ヒートマップ（上位N件）"],
    horizontal=True,
)

st.divider()

# ═══════════════════════════════════════════════════════════════════════════════
# Mode A: Similarity ranking for a specific ad
# ═══════════════════════════════════════════════════════════════════════════════
if mode == "特定広告との類似度ランキング":
    ad_options = {
        a["id"]: f"[{a['id']}] {a['filename']}" for a in ads if a["id"] in embeddings
    }
    default_id = st.session_state.get("selected_ad_id", ids_with_emb[0])
    if default_id not in ad_options:
        default_id = ids_with_emb[0]

    query_id = st.selectbox(
        "基準広告",
        options=list(ad_options.keys()),
        format_func=lambda x: ad_options[x],
        index=list(ad_options.keys()).index(default_id),
    )
    top_n = st.slider("上位 N 件表示", 5, 30, 10)

    q_vec = embeddings[query_id]
    sims = [
        {
            "ad_id": rid,
            "ファイル名": ad_map[rid]["filename"] if rid in ad_map else "—",
            "類似度": cosine(q_vec, rvec),
            "書き起こし（抜粋）": (ad_map[rid].get("full_text") or "")[:70]
            if rid in ad_map
            else "",
        }
        for rid, rvec in embeddings.items()
        if rid != query_id
    ]
    sims.sort(key=lambda x: x["類似度"], reverse=True)
    top = sims[:top_n]

    df = pd.DataFrame(top)
    df["類似度"] = df["類似度"].round(3)

    # Bar chart
    fig = px.bar(
        df,
        x="ad_id",
        y="類似度",
        color="類似度",
        color_continuous_scale="RdYlGn",
        range_color=[0.5, 1.0],
        hover_data=["ファイル名", "書き起こし（抜粋）"],
        labels={"ad_id": "広告 ID", "類似度": "コサイン類似度"},
    )
    fig.update_layout(
        height=320, margin={"l": 0, "r": 0, "t": 10, "b": 0}, showlegend=False
    )
    fig.add_hline(
        y=0.95, line_dash="dash", line_color="red", annotation_text="0.95 (高類似)"
    )
    st.plotly_chart(fig, use_container_width=True)

    st.dataframe(df, use_container_width=True, hide_index=True)

    # Click to select
    if st.button("この広告を詳細ページで開く"):
        st.session_state["selected_ad_id"] = query_id
        st.switch_page("pages/2_🔍_広告詳細.py")

# ═══════════════════════════════════════════════════════════════════════════════
# Mode B: Heatmap
# ═══════════════════════════════════════════════════════════════════════════════
else:
    n = st.slider(
        "対象件数（最新 N 件）",
        10,
        min(60, len(ids_with_emb)),
        min(30, len(ids_with_emb)),
    )
    target_ids = ids_with_emb[-n:]

    matrix = [
        [round(cosine(embeddings[i], embeddings[j]), 3) for j in target_ids]
        for i in target_ids
    ]

    labels = [f"{i}" for i in target_ids]
    heatmap_df = pd.DataFrame(matrix, index=labels, columns=labels)

    fig = px.imshow(
        heatmap_df,
        color_continuous_scale="RdYlGn",
        zmin=0.5,
        zmax=1.0,
        labels={"color": "類似度"},
        aspect="auto",
    )
    fig.update_layout(
        height=600,
        xaxis_title="広告 ID",
        yaxis_title="広告 ID",
        margin={"l": 0, "r": 0, "t": 10, "b": 0},
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        "対角線（自己類似度=1.0）は除外して解釈してください。0.95以上のペアが同一CM候補です。"
    )
