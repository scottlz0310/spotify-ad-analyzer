# Tasks

プロジェクトのタスク管理ファイル。完了・追加時は必ず日付を記入してください。
**1タスク = 1 PR** の粒度で管理します。

---

## 進行中

_なし_

---

## 未着手

### Phase 2 — コア解析パイプライン

- [ ] `feat/repo-scaffold` — プロジェクト骨格
  - [ ] `pyproject.toml`（uv / ruff / basedpyright / pytest 設定込み）
  - [ ] `uv.lock` 生成
  - [ ] `Dockerfile`（`ghcr.io/astral-sh/uv` 採用）
  - [ ] `docker-compose.yml`（shared/ / data/ マウント）
  - [ ] `.pre-commit-config.yaml`（ruff-format, ruff, basedpyright）
  - [ ] `.gitignore` 更新（Python 用：`.venv/` `__pycache__/` `data/` `shared/` `.coverage`）
  - [ ] `src/__init__.py` / `src/config.py`（環境変数一元管理）
  - [ ] `tests/__init__.py`

- [ ] `feat/db-schema` — SQLite スキーマ + CRUD
  - [ ] `src/db.py`（`ads` / `segments` / `transcripts` / `voice_embeddings` / `llm_analyses` テーブル定義）
  - [ ] CRUD ヘルパー関数（型注釈必須）
  - [ ] `tests/test_db.py`（インメモリ DB 使用）

- [ ] `feat/transcriber` — faster-whisper 文字起こし
  - [ ] `src/transcriber.py`（`WHISPER_MODEL` 環境変数対応）
  - [ ] タイムスタンプ付きセグメントを `TypedDict` で返す
  - [ ] `tests/test_transcriber.py` + `tests/fixtures/sample.wav`（ダミー音声）

- [ ] `feat/diarizer` — pyannote-audio 話者分離
  - [ ] `src/diarizer.py`（pyannote-audio 3.x ラッパー）
  - [ ] `SPEAKER_XX` ラベルと時間範囲を `TypedDict` で返す
  - [ ] `tests/test_diarizer.py`（モック使用）

- [ ] `feat/embedder` — resemblyzer Voice Embedding
  - [ ] `src/embedder.py`（256-dim float32 embedding 生成）
  - [ ] numpy array を SQLite BLOB へシリアライズ / デシリアライズ
  - [ ] `tests/test_embedder.py`

- [ ] `feat/pipeline` — パイプライン統合
  - [ ] `src/pipeline.py`（transcriber → diarizer → embedder → db 保存）
  - [ ] エラー時の `status = 'error'` 更新と例外ログ
  - [ ] `tests/test_pipeline.py`（各モジュールをモック）

- [ ] `feat/watcher-entrypoint` — ファイル監視 + エントリポイント
  - [ ] `src/watcher.py`（watchdog で `shared/` 監視、`spotify_ad_*.wav` を pipeline へ）
  - [ ] `src/main.py`（watcher 起動・SIGINT/SIGTERM graceful shutdown）
  - [ ] `tests/test_watcher.py`

- [ ] `feat/docs` — ドキュメント整備
  - [ ] `README.md`（セットアップ・`docker compose up` 起動手順）
  - [ ] `spotify-ad-analyzer.md`（アーキテクチャ仕様書）

### Phase 3 — LLM 解析（Ollama）

- [ ] `feat/llm-analyzer` — Ollama クライアント + プロンプト
  - [ ] `src/llm_analyzer.py`（Ollama REST API クライアント）
  - [ ] プロンプトテンプレート（商品名・広告種別・スクリプト要約・トーン抽出）
  - [ ] `tests/test_llm_analyzer.py`（Ollama HTTP をモック）

- [ ] `feat/llm-integration` — パイプラインへの LLM 統合
  - [ ] `src/pipeline.py` に LLM ステップ追加
  - [ ] `llm_analyses` テーブルへの保存
  - [ ] 既存テスト更新 + 統合テスト追加

### Phase 4 — パターン分析

- [ ] `feat/pattern-analyzer` — SQL 集計 + CLI レポート
  - [ ] `src/pattern_analyzer.py`（時間帯別頻度・繰り返し声紋・広告種別集計）
  - [ ] CLI コマンド（`python -m src.pattern_analyzer report`）
  - [ ] `tests/test_pattern_analyzer.py`（インメモリ DB 使用）

---

## 完了

### リポジトリ初期整備（Initial commit） — 2026-03-13

- [x] `README.md` / `.gitignore` 追加

### ドキュメント整備（docs/initial-setup） — 2026-03-13

- [x] `README.md` 全面書き直し（アーキテクチャ・パイプライン・uv/Docker 手順）
- [x] `LICENSE` 追加（MIT 2026）
- [x] `tasks.md` 追加（Phase 2〜4、11 PR 計画）
- [x] `.github/copilot-instructions.md` 追加（AI エージェント向け規約）
