# spotify-ad-analyzer — アーキテクチャ仕様書

## 1. 概要

`spotify-ad-analyzer` は、姉妹リポジトリ [`spotify-ad-recorder`](https://github.com/scottlz0310/spotify-ad-recorder)（C# / Windows）が録音した Spotify 広告 WAV ファイルを受け取り、以下の解析を自動実行するパイプラインです。

| ステップ | 技術 | 出力 |
|----------|------|------|
| 文字起こし | faster-whisper（CPU int8） | 全文テキスト + タイムスタンプ付きセグメント |
| 話者分離 | pyannote-audio 4.x | 話者ラベル付き時間区間 |
| 声紋抽出 | resemblyzer | 256-dim float32 embedding |
| 永続化 | SQLite（WAL モード） | `data/ads.db` |
| LLM 解析 | Ollama（Phase 3） | 商品名・広告種別・要約・トーン |
| パターン分析 | SQL 集計（Phase 4） | 時間帯別頻度・繰り返し検出レポート |

---

## 2. システム構成

```
[spotify-ad-recorder (Windows)]
  └── shared/spotify_ad_yyyy-MM-dd_HH-mm-ss.wav
                │
          bind mount
                │
[Docker コンテナ: analyzer]
                │
         src/main.py  ←── SIGINT / SIGTERM で graceful shutdown
                │
         src/watcher.py  ←── watchdog Observer（Linux inotify）
                │  spotify_ad_*.wav を検出
                ▼
         src/pipeline.py  ←── run_pipeline()
          ├── src/transcriber.py  ──→ TranscriptResult
          ├── src/diarizer.py     ──→ DiarizationResult
          ├── src/embedder.py     ──→ EmbeddingResult（256-dim）
          └── src/db.py           ──→ data/ads.db（SQLite）
```

---

## 3. コンポーネント詳細

### 3.1 `src/main.py` — エントリポイント

```python
python -m src.main
```

起動フロー：
1. ロギング設定（INFO レベル → stdout）
2. `db.init_db()` でスキーマ初期化（テーブルが存在しない場合のみ作成）
3. SIGINT / SIGTERM ハンドラを `threading.Event` で登録
4. `start_watcher()` で watchdog オブザーバー起動
5. `stop_event.wait()` でブロック（シグナル受信まで待機）
6. `observer.stop()` → `observer.join()` でクリーンシャットダウン

### 3.2 `src/watcher.py` — ファイル監視

| 公開シンボル | 説明 |
|-------------|------|
| `is_ad_file(path)` | `spotify_ad_*.wav` パターン照合 |
| `AdFileHandler` | `FileSystemEventHandler` サブクラス。`on_closed()` が `IN_CLOSE_WRITE` に対応 |
| `start_watcher(watch_dir, db_path)` | Observer を生成・起動し `ObserverProtocol` を返す |

**重複排除**: `_seen: OrderedDict[str, None]`（上限 256 件）で同一パスの二重処理を防止。  
パイプライン失敗時は `_seen` から削除してリトライを許可。

### 3.3 `src/transcriber.py` — 文字起こし

```python
result = transcribe(audio_path)  # -> TranscriptResult
```

- `faster-whisper` の `WhisperModel` を使用（`WHISPER_MODEL` 環境変数で切替、デフォルト `small`）
- `compute_type="int8"` で CPU 推論
- `TranscriptResult.segments`: `TranscriptSegment(text, start_sec, end_sec)` のリスト

### 3.4 `src/diarizer.py` — 話者分離

```python
result = diarize(audio_path)  # -> DiarizationResult
```

- `pyannote.audio` の `Pipeline` を使用（`DIARIZE_MODEL` 環境変数で切替）
- `HF_TOKEN` 環境変数が必要（Hugging Face アクセストークン）
- `DiarizationResult.segments`: `DiarizationSegment(speaker, start_sec, end_sec)` のリスト

### 3.5 `src/embedder.py` — 声紋抽出

```python
result = embed(audio_path)  # -> EmbeddingResult
```

- `resemblyzer` の `VoiceEncoder` で全体音声から 256-dim float32 ベクトルを生成
- `embedding_to_blob(arr)` / `blob_to_embedding(blob)` で SQLite BLOB との相互変換

### 3.6 `src/pipeline.py` — パイプライン統合

```python
result = run_pipeline(audio_path, db_path)  # -> PipelineResult
```

処理フロー：
1. `db.insert_ad()` → `status = "processing"`
2. `transcribe()` → `diarize()` → `embed()` を順次実行
3. `_assign_speakers()` で文字起こしセグメントに話者を割り当て（2-pointer O(N+M)）
4. `db.upsert_transcript()` / `db.insert_segments()` / `db.upsert_voice_embedding()`
5. `status = "done"`
6. 例外発生時: `status = "error"` に更新し `RuntimeError` に包んで再 raise

**注意**: 声紋は話者ごとではなく音声全体から 1 件抽出（`speaker=""`）。  
複数話者の区別は `segments` テーブルの `speaker` カラムで管理。

### 3.7 `src/db.py` — データベース

SQLite（WAL モード、外部キー有効）。`data/ads.db` に永続化。

---

## 4. データベーススキーマ

### `ads` テーブル

| カラム | 型 | 説明 |
|--------|----|------|
| `id` | INTEGER PK | 自動採番 |
| `filename` | TEXT UNIQUE | WAV ファイル名（例: `spotify_ad_2026-01-01_12-00-00.wav`） |
| `recorded_at` | TEXT | ISO-8601 録音日時（例: `2026-01-01T12:00:00Z`） |
| `status` | TEXT | `pending` / `processing` / `done` / `error` |
| `error_message` | TEXT | エラー発生時のトレースバック |
| `created_at` | TEXT | 作成日時（UTC） |
| `updated_at` | TEXT | 更新日時（UTC） |

### `segments` テーブル

| カラム | 型 | 説明 |
|--------|----|------|
| `id` | INTEGER PK | 自動採番 |
| `ad_id` | INTEGER FK→ads | 広告 ID |
| `speaker` | TEXT | 話者ラベル（`SPEAKER_00` など、不明時は `""`） |
| `text` | TEXT | 文字起こしテキスト |
| `start_sec` | REAL | セグメント開始秒 |
| `end_sec` | REAL | セグメント終了秒 |

### `transcripts` テーブル

| カラム | 型 | 説明 |
|--------|----|------|
| `ad_id` | INTEGER PK FK→ads | 広告 ID |
| `full_text` | TEXT | 全文テキスト |
| `language` | TEXT | 検出言語コード（例: `ja`） |
| `whisper_model` | TEXT | 使用モデル名（例: `small`） |

### `voice_embeddings` テーブル

| カラム | 型 | 説明 |
|--------|----|------|
| `id` | INTEGER PK | 自動採番 |
| `ad_id` | INTEGER FK→ads | 広告 ID |
| `speaker` | TEXT | 話者ラベル（現状は常に `""`） |
| `embedding` | BLOB | 256-dim float32 配列（numpy → bytes） |

UNIQUE 制約: `(ad_id, speaker)`

### `llm_analyses` テーブル（Phase 3 で利用）

| カラム | 型 | 説明 |
|--------|----|------|
| `ad_id` | INTEGER PK FK→ads | 広告 ID |
| `product_name` | TEXT | 商品・サービス名 |
| `ad_type` | TEXT | 広告種別（音楽 / ナレーション / ドラマ仕立て など） |
| `summary` | TEXT | スクリプト要約 |
| `tone` | TEXT | トーン・感情（明るい / シリアス など） |
| `raw_response` | TEXT | LLM の生レスポンス |
| `analyzed_at` | TEXT | 解析日時（UTC） |

> すべてのテーブルは `ads(id) ON DELETE CASCADE` で連携しており、広告レコードを削除すると関連データもすべて削除されます。

---

## 5. 環境変数リファレンス

| 変数名 | デフォルト値 | 説明 |
|--------|-------------|------|
| `SHARED_DIR` | `/app/shared` | 監視対象ディレクトリ |
| `DATA_DIR` | `/app/data` | SQLite 保存先ディレクトリ |
| `WHISPER_MODEL` | `small` | faster-whisper モデルサイズ（`tiny`/`base`/`small`/`medium`/`large-v3`） |
| `HF_TOKEN` | `""` | Hugging Face アクセストークン（pyannote-audio 必須） |
| `DIARIZE_MODEL` | `pyannote/speaker-diarization-3.1` | 話者分離モデル ID |
| `OLLAMA_HOST` | `host.docker.internal:11434` | Ollama API ホスト（Phase 3） |

---

## 6. ファイル命名規則

姉妹リポジトリとのインターフェース：

```
spotify_ad_yyyy-MM-dd_HH-mm-ss.wav
```

例：`spotify_ad_2026-03-14_18-30-00.wav`

パターン照合は `is_ad_file()` で行い、`spotify_ad_*.wav` に一致するファイルのみ処理します。

---

## 7. Docker 構成

```yaml
# docker-compose.yml（抜粋）
services:
  analyzer:
    build: .
    volumes:
      - ./shared:/app/shared   # spotify-ad-recorder の出力先をマウント
      - ./data:/app/data       # SQLite 永続化
    environment:
      HF_TOKEN: ${HF_TOKEN:-}  # 未設定時は空文字。話者分離機能を使う場合は必須
      WHISPER_MODEL: ${WHISPER_MODEL:-small}
      OLLAMA_HOST: ${OLLAMA_HOST:-host.docker.internal:11434}
    restart: unless-stopped
```

> **注意**: `HF_TOKEN` が未設定（または空）でもコンテナは起動しますが、
> 話者分離ステップ（`diarize()`）で認証エラーが発生し、パイプラインが失敗します。
> シェル環境変数を優先します。未設定の場合は `.env` ファイル（gitignore 済み）がフォールバックとして使われます。

`Dockerfile` は `python:3.12-slim` ベース。  
`ghcr.io/astral-sh/uv` から `uv` バイナリを COPY して `uv sync --frozen` でインストール。

---

## 8. 今後のフェーズ

### Phase 3 — LLM 解析（`feat/llm-analyzer`）

- `src/llm_analyzer.py`: Ollama REST API クライアント（`/api/generate`）
- プロンプトテンプレート: 商品名・広告種別・スクリプト要約・トーン抽出
- `src/pipeline.py` への統合: 文字起こし完了後に LLM を呼び出し `llm_analyses` テーブルへ保存

### Phase 4 — パターン分析（`feat/pattern-analyzer`）

- `src/pattern_analyzer.py`: SQL 集計クエリ
  - 時間帯別広告頻度
  - 声紋類似度による繰り返し広告検出
  - 広告種別・トーン分布
- CLI コマンド: `python -m src.pattern_analyzer report`
