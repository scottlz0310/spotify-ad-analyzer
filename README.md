# spotify-ad-analyzer

[`spotify-ad-recorder`](https://github.com/scottlz0310/spotify-ad-recorder) が録音した Spotify 広告 WAV ファイルを自動検出し、文字起こし・話者分離・声紋抽出・LLM 解析を行うパイプライン。

- `shared/` ディレクトリを監視して新規 `.wav` を自動処理
- CPU 専用 Docker（Linux）で完結、GPU 不要
- 解析結果は SQLite（`data/ads.db`）に蓄積
- Phase 3 以降は Ollama（ローカル LLM）でオフライン解析

詳細仕様は [`spotify-ad-analyzer.md`](spotify-ad-analyzer.md) を参照。（実装後に追加予定）

---

## 前提条件

| 要件 | 内容 |
|------|------|
| OS | Windows / macOS / Linux |
| ランタイム | [Docker Desktop](https://www.docker.com/products/docker-desktop/) |
| 姉妹リポジトリ | [`spotify-ad-recorder`](https://github.com/scottlz0310/spotify-ad-recorder)（WAV ファイルの生成元） |

> ローカル開発（Docker なし）には [uv](https://docs.astral.sh/uv/) が必要です。

---

## セットアップ

```powershell
# リポジトリをクローン
git clone https://github.com/scottlz0310/spotify-ad-analyzer.git
cd spotify-ad-analyzer
```

`spotify-ad-recorder` の `shared/` ディレクトリをマウントするか、
ローカルに `shared/` フォルダを作成して WAV ファイルを配置してください。

---

## 実行

```bash
# イメージビルド + コンテナ起動
docker compose up --build

# バックグラウンド起動
docker compose up -d --build

# ログ確認
docker compose logs -f analyzer
```

---

## ローカル開発（uv）

```bash
# 仮想環境作成 + 依存関係インストール
uv sync --all-extras

# pre-commit フック登録
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
shared/spotify_ad_*.wav
        │
        ▼ watchdog（ファイル監視）
        ├── faster-whisper     → 文字起こし + タイムスタンプ
        ├── pyannote-audio     → 話者分離
        ├── resemblyzer        → Voice Embedding（256-dim）
        └── SQLite             → data/ads.db
              ├── [Phase 3] Ollama  → 広告解析テキスト
              └── [Phase 4] SQL 集計 → パターンレポート
```

---

## ステータス

現在はリポジトリ初期整備フェーズです。実装は `tasks.md` のタスクに従い進行します。

---

## ライセンス

MIT
