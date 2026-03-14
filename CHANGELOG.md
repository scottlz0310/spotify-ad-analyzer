# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

### Added
- `src/llm_analyzer.py` — Ollama REST API クライアント（`analyze_transcript()`、`_parse_response()`、Markdown コードフェンス除去、JSON パース失敗時のフォールバック）
- `LlmAnalysisResult` — `__slots__` + `@final` + `@override __repr__` 結果クラス（`product_name`・`ad_type`・`summary`・`tone`・`raw_response`）
- `OllamaError(RuntimeError)` — Ollama 接続失敗・非 JSON レスポンス時の例外クラス
- `tests/test_llm_analyzer.py` — 17 テスト（HTTP モック、コードフェンス除去、Invalid JSON フォールバック、非 dict JSON 型チェック、カバレッジ 100%）
- `src/config.py` — `OLLAMA_MODEL` 環境変数追加（デフォルト `llama3.2`）
- `docker-compose.yml` — `OLLAMA_MODEL` 環境変数追加
- `src/pipeline.py` — 解析パイプライン統合（transcriber → diarizer → embedder → db 保存、DI 対応、エラー時 `status='error'` 設定）
- `tests/test_pipeline.py` — 14 テスト（全モジュールをモック、カバレッジ 97%）
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
