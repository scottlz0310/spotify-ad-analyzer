# Tasks

プロジェクトのタスク管理ファイル。完了・追加時は必ず日付を記入してください。
**1タスク = 1 PR** の粒度で管理します。

---

## 進行中

_なし_

---

## 未着手

_なし_

---

## 完了

### WAV 分割（feat/wav-splitter） — 2026-03-14

- [x] `src/splitter.py`（無音区間検出・WAV 分割・`split_if_needed` オーケストレーター）
- [x] `src/watcher.py` — `split_fn` DI 追加・`_handle()` マルチパート対応
- [x] `tests/test_splitter.py`（21 テスト）・`tests/test_watcher.py`（5 テスト追加）

### パターン分析 CLI（feat/pattern-analyzer）— 2026-03-14

- [x] `src/pattern_analyzer.py`（時間帯別頻度・広告種別分布・トーン分布・cosine 類似度による繰り返し声紋検出）
- [x] `PatternReport` 結果クラス（`to_dict()` → JSON 出力）
- [x] CLI コマンド（`python -m src.pattern_analyzer report --db PATH --threshold FLOAT`）
- [x] `tests/test_pattern_analyzer.py`（19 テスト、tmp_path SQLite、カバレッジ 93%）

### LLM パイプライン統合（feat/llm-integration） — 2026-03-14

- [x] `src/pipeline.py`: `_AnalyzeFnProtocol`・`_default_analyze`（OllamaError 時 graceful degradation）・`analyze_fn` DI パラメータ追加
- [x] `PipelineResult`: `llm_analysis: LlmAnalysisResult | None` フィールド追加
- [x] `db.upsert_llm_analysis` で `llm_analyses` テーブルへ永続化
- [x] `tests/test_pipeline.py`: 既存 13 テスト hermetic 化 + 新規 3 テスト追加（計 16 テスト）

### Ollama クライアント（feat/llm-analyzer） — 2026-03-14

- [x] `src/llm_analyzer.py`（Ollama REST API クライアント、urllib 使用）
- [x] プロンプトテンプレート（商品名・広告種別・スクリプト要約・トーン抽出）
- [x] `tests/test_llm_analyzer.py`（Ollama HTTP をモック、17 テスト、カバレッジ 100%）
- [x] `src/config.py`: `OLLAMA_MODEL` 環境変数追加
- [x] `docker-compose.yml`: `OLLAMA_MODEL` 追加

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
