# spotify-ad-analyzer

[`spotify-ad-recorder`](https://github.com/scottlz0310/spotify-ad-recorder) が録音した Spotify 広告 WAV ファイルを自動検出し、文字起こし・話者分離・声紋抽出・LLM 解析を行うパイプライン。

- `shared/` ディレクトリを監視して新規 `.wav` を自動処理
- CPU 専用 Docker（Linux）で完結、GPU 不要
- 解析結果は SQLite（`data/ads.db`）に蓄積
- Phase 3 以降は Ollama（ローカル LLM）でオフライン解析

詳細仕様は [`spotify-ad-analyzer.md`](./spotify-ad-analyzer.md) を参照。

---

## 前提条件

| 要件 | 内容 |
|------|------|
| OS | Windows / macOS / Linux |
| ランタイム | Docker Desktop（Windows / macOS）または Docker Engine（Linux） |
| 姉妹リポジトリ | [`spotify-ad-recorder`](https://github.com/scottlz0310/spotify-ad-recorder)（WAV ファイルの生成元） |
| Hugging Face トークン | pyannote-audio の話者分離モデル利用に必要（`HF_TOKEN`） |

> ローカル開発（Docker なし）には [uv](https://docs.astral.sh/uv/) が必要です。

---

## セットアップ

```powershell
# リポジトリをクローン
git clone https://github.com/scottlz0310/spotify-ad-analyzer.git
cd spotify-ad-analyzer
```

### 環境変数

シェル環境変数を優先します。未設定の場合はプロジェクトルートの `.env` ファイルがフォールバックとして使われます（docker compose が自動で読み込みます）。

| 変数 | 必須 | デフォルト | 説明 |
|------|:----:|-----------|------|
| `HF_TOKEN` | ✅ | — | Hugging Face アクセストークン |
| `WHISPER_MODEL` | | `small` | `tiny` / `base` / `small` / `medium` / `large-v3` |
| `OLLAMA_HOST` | | `host.docker.internal:11434` | Ollama ホスト（Phase 3） |
| `WATCHDOG_FORCE_POLLING` | | `0` | `1` で PollingObserver（Docker Desktop / Windows 環境で必要） |

```powershell
# 方法A: シェル環境変数（推奨）
$env:HF_TOKEN = "hf_xxxxxxxxxxxxxxxxxxxx"
# Docker Desktop (Windows) の場合はポーリングモードを有効化
$env:WATCHDOG_FORCE_POLLING = "1"
docker compose up

# 方法B: .env ファイル（フォールバック、gitignore 済み）
# HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxx
```

> `HF_TOKEN` の取得: [Hugging Face の設定ページ](https://huggingface.co/settings/tokens) でアクセストークンを生成し、  
> [`pyannote/speaker-diarization-3.1`](https://huggingface.co/pyannote/speaker-diarization-3.1) モデルへのアクセスを承認してください。

### 共有ディレクトリの準備

`spotify-ad-recorder` の `shared/` をマウントするか、ローカルに作成します。

```powershell
mkdir shared
mkdir data
```

---

## 実行

```bash
# イメージビルド + コンテナ起動（フォアグラウンド）
docker compose up --build

# バックグラウンド起動
docker compose up -d --build

# ログ確認
docker compose logs -f analyzer

# 停止
docker compose down
```

---

## Web ダッシュボード

`docker compose up` と同時に Streamlit ダッシュボードも起動します。

```
http://localhost:8501
```

| ページ | 内容 |
|--------|------|
| **🎵 トップ** | 広告総数・文字起こし済み件数・平均時間のサマリー |
| **📋 広告一覧** | 処理済み WAV の一覧（ステータス・言語・時間でフィルタリング可能） |
| **🔍 広告詳細** | 文字起こし全文・話者セグメント・LLM 解析結果 |
| **🔊 話者類似度** | Voice Embedding（256-dim）を使ったコサイン類似度マトリクス |

---

## ローカル開発（uv）

```bash
# 仮想環境作成 + 依存関係インストール（初回）
uv sync --all-groups

# pre-commit フック登録（初回のみ）
uv run pre-commit install

# テスト（並列 + カバレッジ）
uv run pytest -n auto --cov=src --cov-report=term-missing

# Lint / Format / 型チェック
uv run ruff format .
uv run ruff check . --fix
uv run basedpyright
```

---

## パイプライン概要

```
spotify-ad-recorder
└── shared/spotify_ad_yyyy-MM-dd_HH-mm-ss.wav
            │
            ▼  src/watcher.py（watchdog inotify IN_CLOSE_WRITE）
            │
            ▼  src/pipeline.py
            ├── src/transcriber.py  ─── faster-whisper → 文字起こし + タイムスタンプ
            ├── src/diarizer.py     ─── pyannote-audio → 話者分離セグメント
            ├── src/embedder.py     ─── resemblyzer    → Voice Embedding（256-dim）
            └── src/db.py           ─── SQLite（data/ads.db）
                  ├── [Phase 3] src/llm_analyzer.py ─ Ollama → 広告テキスト解析
                  └── [Phase 4] src/pattern_analyzer.py ─ SQL 集計 → パターンレポート
```

---

## ステータス

| フェーズ | 内容 | 状態 |
|----------|------|------|
| Phase 1  | CI・DB・プロジェクト骨格 | ✅ 完了 |
| Phase 2  | 文字起こし・話者分離・声紋抽出・パイプライン・監視・ドキュメント | ✅ 完了 |
| Phase 3  | Ollama LLM 解析 | 🔜 未着手 |
| Phase 4  | パターン分析 CLI | 🔜 未着手 |

---

## ライセンス

MIT
