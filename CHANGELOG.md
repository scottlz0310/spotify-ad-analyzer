# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

### Changed
- uv バージョン管理を `pyproject.toml` の `[tool.uv] required-version` に一本化。CI workflow は `pyproject.toml` を読み取って GitHub Releases の該当 artifact を checksum 検証付きでインストールし、`Dockerfile`/`dashboard/Dockerfile` は `ARG UV_VERSION` で外出し。`renovate.json` に GitHub Releases datasource の customManager を追加し、release artifact の反映ラグを `minimumReleaseAge: "3 days"` で吸収するようにした。

---

## [0.7.0]

### Added
- `dashboard/` — Streamlit Web ダッシュボード（`docker compose up dashboard` で起動、ポート 8501）
  - **概要ページ** — 総広告数・書き起こし済み数・平均尺など KPI + 直近 10 件一覧
  - **広告一覧ページ** — テキスト検索・言語/話者数/尺フィルタ付きテーブル
  - **広告詳細ページ** — 全文書き起こし・話者タイムライン（Plotly・MM:SS軸）・WAV 再生・セグメント表・LLM 解析
  - **話者類似度ページ** — コサイン類似度ランキングバーチャート / 全件ヒートマップ
- `docker-compose.yml` に `dashboard` サービス追加（ポート 8501、`depends_on: analyzer`）

---

## [0.6.0]

### Added
- `src/splitter.py` — WAV 無音区間検出 + 分割モジュール（`_rms_chunks`・`detect_silence_boundary`・`split_wav`・`split_if_needed`）
- `tests/test_splitter.py` — 21 テスト（合成 WAV・境界検出精度・分割ファイル検証）

### Changed
- `src/watcher.py` — `_SplitFnProtocol`・`_default_split` 追加・`AdFileHandler` に `split_fn` DI パラメータ追加・`_handle()` をマルチパート対応にリファクタリング（テンポラリファイル自動クリーンアップ）
- `tests/test_watcher.py` — `_make_handler` に no-op splitter 注入・split 動作テスト 5 件追加

---

## [0.5.0]

### Added
- `src/pattern_analyzer.py`— SQL 集計 + CLI レポート（`hourly_frequency`・`ad_type_distribution`・`tone_distribution`・`detect_repeat_ads`、`PatternReport` 結果クラス、`python -m src.pattern_analyzer report` CLI）
- `tests/test_pattern_analyzer.py` — 25 テスト（tmp_path SQLite、cosine 類似度テスト、threshold バリデーションテスト、`main()` CLI テスト含む）

### Changed (from [Unreleased])
- `src/llm_analyzer.py` — Ollama REST API クライアント（`analyze_transcript()`、`_parse_response()`、Markdown コードフェンス除去、JSON パース失敗時のフォールバック）
- `LlmAnalysisResult` — `__slots__` + `@final` + `@override __repr__` 結果クラス（`product_name`・`ad_type`・`summary`・`tone`・`raw_response`）
- `OllamaError(RuntimeError)` — Ollama 接続失敗・非 JSON レスポンス時の例外クラス
- `tests/test_llm_analyzer.py` — 17 テスト（HTTP モック、コードフェンス除去、Invalid JSON フォールバック、非 dict JSON 型チェック、カバレッジ 100%）
- `src/config.py` — `OLLAMA_MODEL` 環境変数追加（デフォルト `llama3.2`）
- `docker-compose.yml` — `OLLAMA_MODEL` 環境変数追加
- `src/pipeline.py` — LLM 解析ステップ統合（`_AnalyzeFnProtocol`・`_default_analyze`・`analyze_fn` DI パラメータ、`OllamaError` 時はログを残して graceful degradation、`db.upsert_llm_analysis` で永続化）
- `PipelineResult` — `llm_analysis: LlmAnalysisResult | None` フィールド追加
- `tests/test_pipeline.py` — 既存テストを hermetic 化（`analyze_fn=lambda _: None`）、LLM 結果永続化・スキップ・フィールド検証テスト 3 件追加（計 16 テスト）
- `src/watcher.py` — watchdog ファイル監視（`spotify_ad_*.wav` を検出して pipeline 実行、`IN_CLOSE_WRITE` 対応、重複実行防止）
- `src/main.py` — エントリポイント実装（ログ設定、DB 初期化、SIGINT/SIGTERM graceful shutdown）
- `tests/test_watcher.py` / `tests/test_main.py` — 計 17 テスト（カバレッジ 100% / 89%）
- `spotify-ad-analyzer.md` — アーキテクチャ仕様書（コンポーネント・DB スキーマ・環境変数・将来フェーズ）
- `README.md` — セットアップ手順刷新（`HF_TOKEN` 取得方法・`docker compose` コマンド・フェーズ別ステータス）
- `docker-compose.yml` — `HF_TOKEN` 環境変数を追加

---

## [0.4.0] — 2026-03-14

### Added
- `src/embedder.py` — resemblyzer 声紋埋め込み（256-dim float32、SQLite BLOB シリアライズ対応）
- `tests/test_embedder.py` — 17 テスト（resemblyzer をモック、pkg_resources 問題を回避）
- `src/diarizer.py` — pyannote.audio 4.x ラッパー（`DIARIZE_MODEL` / `HF_TOKEN` 環境変数対応、CPU 専用）
- `tests/test_diarizer.py` — 12 テスト（モック使用、カバレッジ 96%）
- `src/transcriber.py` — faster-whisper ラッパー（`WHISPER_MODEL` 環境変数対応）
- `tests/test_transcriber.py` + `tests/fixtures/sample.wav`

---

## [0.3.0] — 2026-03-14

### Added
- `.github/workflows/ci.yml` — GitHub Actions CI（ruff / basedpyright / pytest / Codecov）
- `renovate.json` — 依存関係自動更新（org 共通プリセット）
- `pyproject.toml`: `--cov-report=xml` 追加（Codecov 連携）

---

## [0.2.0] — 2026-03-14

### Added
- `src/db.py` — SQLite 5 テーブルスキーマ + CRUD ヘルパー（TypedDict / AdStatus Literal / WAL / FK）
- `tests/test_db.py` — 24 テスト（FK カスケード削除含む）

### Changed
- `pyproject.toml`: `PLR0913` を `src/db.py` の per-file-ignores へ移動、`reportAny = false`（sqlite3 stdlib 制約）

---

## [0.1.0] — 2026-03-13

### Added
- `pyproject.toml` — uv / ruff / basedpyright / pytest 設定
- `Dockerfile` + `docker-compose.yml` — CPU 専用コンテナ構成
- `.pre-commit-config.yaml` — ruff + basedpyright フック
- `src/config.py` — 環境変数一元管理（`SHARED_DIR` / `DATA_DIR` / `WHISPER_MODEL` / `OLLAMA_HOST`）
- `src/main.py` — エントリポイント（プレースホルダー）
- `tests/test_config.py` — monkeypatch + importlib.reload テスト
- `README.md` — アーキテクチャ・セットアップ手順
- `LICENSE` — MIT 2026
- `tasks.md` — タスク管理
- `.github/copilot-instructions.md` — AI エージェント向け開発規約
