# Tasks

プロジェクトのタスク管理ファイル。完了・追加時は必ず日付を記入してください。
**1タスク = 1 PR** の粒度で管理します。

---

## 進行中

### Phase 3 — LLM 解析（Ollama）

- [x] `feat/llm-analyzer` — Ollama クライアント + プロンプト
  - [x] `src/llm_analyzer.py`（Ollama REST API クライアント、urllib 使用）
  - [x] プロンプトテンプレート（商品名・広告種別・スクリプト要約・トーン抽出）
  - [x] `tests/test_llm_analyzer.py`（Ollama HTTP をモック、14 テスト、カバレッジ 100%）
  - [x] `src/config.py`: `OLLAMA_MODEL` 環境変数追加
  - [x] `docker-compose.yml`: `OLLAMA_MODEL` 追加

---

## 未着手

### Phase 3 — LLM 解析（Ollama）

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

### resemblyzer 声紋埋め込み（feat/embedder） — 2026-03-14

- [x] `src/embedder.py`（256-dim float32 embedding 生成、256-dim バリデーション付き）
- [x] numpy array を SQLite BLOB へシリアライズ / デシリアライズ
- [x] `tests/test_embedder.py`（17 テスト、resemblyzer モック、カバレッジ 100%）
- [x] `pyproject.toml`: `numpy>=1.26` 追加、`setuptools` 削除、v0.4.0

### pyannote-audio 話者分離（feat/diarizer） — 2026-03-14

- [x] `src/diarizer.py`（pyannote-audio 4.x ラッパー、Protocol パターン、CPU 専用）
- [x] `DiarizationSegment` / `DiarizationResult` クラス（`model_name` フィールド付き）
- [x] `tests/test_diarizer.py`（12 テスト、モック使用）
- [x] `src/config.py`: `HF_TOKEN` / `DIARIZE_MODEL` 環境変数追加

### faster-whisper 文字起こし（feat/transcriber） — 2026-03-14

- [x] `src/transcriber.py`（`WHISPER_MODEL` 環境変数対応、CPU int8 推論）
- [x] `TranscriptSegment` / `TranscriptResult` dataclass 相当クラス
- [x] `tests/test_transcriber.py`（13 テスト、モック使用、カバレッジ 98%）
- [x] `tests/fixtures/sample.wav`（0.5 秒無音 WAV ダミー）

### SQLite スキーマ + CRUD（feat/db-schema） — 2026-03-14

- [x] `src/db.py`（`ads` / `segments` / `transcripts` / `voice_embeddings` / `llm_analyses` テーブル定義）
- [x] CRUD ヘルパー関数（TypedDict + AdStatus Literal、型注釈必須）
- [x] `tests/test_db.py`（24 テスト、カバレッジ 95%、FK カスケード削除含む）

### CI 整備（feat/ci） — 2026-03-14

- [x] `.github/workflows/ci.yml`（push / PR on main で ruff・basedpyright・pytest・Codecov）
- [x] `renovate.json`（依存関係自動更新）
- [x] `pyproject.toml`: `--cov-report=xml` 追加

### リポジトリ初期整備（Initial commit） — 2026-03-13

- [x] `README.md` / `.gitignore` 追加

### ドキュメント整備（docs/initial-setup） — 2026-03-13

- [x] `README.md` 全面書き直し（アーキテクチャ・パイプライン・uv/Docker 手順）
- [x] `LICENSE` 追加（MIT 2026）
- [x] `tasks.md` 追加（Phase 2〜4、11 PR 計画）
- [x] `.github/copilot-instructions.md` 追加（AI エージェント向け規約）

### プロジェクト骨格（feat/repo-scaffold） — 2026-03-13

- [x] `pyproject.toml`（uv / ruff / basedpyright / pytest 設定込み）
- [x] `uv.lock` 生成
- [x] `Dockerfile`（`ghcr.io/astral-sh/uv:0.10.0` 採用、CPU 専用）
- [x] `docker-compose.yml`（shared/ / data/ マウント）
- [x] `.pre-commit-config.yaml`（ruff v0.15.6 + basedpyright ローカルフック）
- [x] `.gitignore` 更新（Python 用）
- [x] `src/__init__.py` / `src/config.py`（環境変数一元管理）
- [x] `src/main.py`（エントリポイント、本実装は feat/watcher-entrypoint）
- [x] `tests/__init__.py` / `tests/test_config.py`（monkeypatch + importlib.reload）
