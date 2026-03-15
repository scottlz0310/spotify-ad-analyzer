# Architecture — spotify-ad-analyzer

## システム概要

`spotify-ad-analyzer` は、姉妹リポジトリ [`spotify-ad-recorder`](https://github.com/scottlz0310/spotify-ad-recorder)（C# / Windows）が録音した Spotify 広告 WAV ファイルを受け取り、文字起こし・話者分離・声紋抽出・LLM 解析を自動実行するパイプラインです。

---

## コンポーネント構成

```
[spotify-ad-recorder (Windows)]
  └── shared/spotify_ad_yyyy-MM-dd_HH-mm-ss.wav
                │
          bind mount
                │
[Docker コンテナ: analyzer]
                │
         src/main.py  ─── SIGINT/SIGTERM → graceful shutdown
                │
         src/watcher.py  ─── watchdog Observer
                │  spotify_ad_*.wav を検出
                ▼
         src/pipeline.py  ─── run_pipeline()
          ├── src/transcriber.py  ──→ TranscriptResult
          ├── src/diarizer.py     ──→ DiarizationResult
          ├── src/embedder.py     ──→ EmbeddingResult (256-dim)
          ├── src/llm_analyzer.py ──→ LlmAnalysisResult
          └── src/db.py           ──→ data/ads.db (SQLite)

[オフライン CLI]
  python -m src.pattern_analyzer report
          └── src/pattern_analyzer.py ──→ PatternReport (JSON)
```

---

## モジュール責務

| モジュール | 責務 |
|-----------|------|
| `src/main.py` | エントリポイント。ロギング設定・DB 初期化・watcher 起動・シグナルハンドリング |
| `src/watcher.py` | `shared/` を watchdog で監視。`spotify_ad_*.wav` のみ pipeline へ渡す（重複排除付き） |
| `src/pipeline.py` | transcriber / diarizer / embedder / llm_analyzer を順次呼び出し DB へ保存。エラー時は `status=error` |
| `src/transcriber.py` | faster-whisper ラッパー。`WHISPER_MODEL` 環境変数でモデルサイズ切替 |
| `src/diarizer.py` | pyannote-audio 4.x ラッパー。`HF_TOKEN` / `DIARIZE_MODEL` 環境変数 |
| `src/embedder.py` | resemblyzer ラッパー。256-dim float32 を SQLite BLOB として保存 |
| `src/llm_analyzer.py` | Ollama REST API クライアント（`/api/generate`）。JSON パース失敗時は graceful degradation |
| `src/pattern_analyzer.py` | SQL 集計 + cosine 類似度による繰り返し広告検出。`python -m` CLI で JSON レポート出力 |
| `src/db.py` | SQLite スキーマ定義・CRUD ヘルパー（WAL / FK 有効） |
| `src/config.py` | 環境変数の一元管理 |

---

## データフロー

```
WAV ファイル検出
      │
      ▼
 transcribe()  →  TranscriptResult
      │              ├── full_text: str
      │              └── segments: list[TranscriptSegment]
      │
      ▼
  diarize()   →  DiarizationResult
      │              └── segments: list[DiarizationSegment]
      │
      ▼
 _assign_speakers()  →  各セグメントに話者ラベルを付与（2-pointer O(N+M)）
      │
      ▼
   embed()    →  EmbeddingResult
      │              └── embedding: ndarray[float32, 256-dim]
      │
      ▼
llm_analyze()  →  LlmAnalysisResult | None
      │              ├── product_name, ad_type, summary, tone
      │              └── OllamaError 発生時は None（graceful degradation）
      │
      ▼
  db.py  →  ads / transcripts / segments / voice_embeddings / llm_analyses
```

---

## データベーススキーマ

```
ads
 ├── id INTEGER PK
 ├── filename TEXT UNIQUE        # spotify_ad_yyyy-MM-dd_HH-mm-ss.wav
 ├── recorded_at TEXT            # ISO-8601
 ├── status TEXT                 # pending / processing / done / error
 ├── error_message TEXT
 ├── created_at TEXT
 └── updated_at TEXT

transcripts (ad_id PK → ads)
 ├── full_text TEXT
 ├── language TEXT               # 検出言語コード（例: ja）
 └── whisper_model TEXT

segments (ad_id FK → ads)
 ├── speaker TEXT                # SPEAKER_00 など
 ├── text TEXT
 ├── start_sec REAL
 └── end_sec REAL

voice_embeddings (ad_id FK → ads, UNIQUE(ad_id, speaker))
 ├── speaker TEXT                # 現状は常に ""（全体音声）
 └── embedding BLOB              # 256 × float32 = 1024 bytes

llm_analyses (ad_id PK → ads)
 ├── product_name TEXT
 ├── ad_type TEXT
 ├── summary TEXT
 ├── tone TEXT
 ├── raw_response TEXT
 └── analyzed_at TEXT
```

> すべての子テーブルは `ON DELETE CASCADE` で連携。

---

## 外部インターフェース

| 境界 | 形式 | 説明 |
|------|------|------|
| 録音ファイル受け取り | `spotify_ad_yyyy-MM-dd_HH-mm-ss.wav` | `shared/` bind mount 経由 |
| DB 出力 | `data/ads.db`（SQLite） | `data/` bind mount 経由 |
| LLM | Ollama REST `POST /api/generate` | `OLLAMA_HOST` 環境変数で指定 |
| 声紋モデル | HuggingFace Hub（`pyannote/speaker-diarization-3.1`） | `HF_TOKEN` 必須 |
| レポート出力 | JSON（stdout） | `python -m src.pattern_analyzer report` |

---

## 技術スタック

| 分類 | 技術 |
|------|------|
| 言語 | Python 3.12 |
| パッケージ管理 | uv |
| 実行環境 | Docker（linux/amd64、CPU 専用） |
| 文字起こし | faster-whisper（int8 CPU 推論） |
| 話者分離 | pyannote-audio 4.x |
| 声紋抽出 | resemblyzer（256-dim float32） |
| LLM | Ollama（ローカル、オフライン） |
| DB | SQLite（WAL モード） |
| テスト | pytest + pytest-cov + pytest-xdist |
| Lint / Format | ruff |
| 型チェック | basedpyright（typeCheckingMode = all） |
