# Usage Guide — spotify-ad-analyzer

## 前提条件

| 必要なもの | 確認方法 |
|-----------|---------|
| Docker Desktop（起動済み） | `docker info` |
| Hugging Face アクセストークン | [hf.co/settings/tokens](https://huggingface.co/settings/tokens) で取得 |
| pyannote モデル利用承認 | [pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1) で "Agree and access repository" |
| Ollama（任意・LLM 解析を使う場合） | [ollama.com](https://ollama.com/) からインストール |

---

## セットアップ

### 1. リポジトリのクローン

```powershell
git clone https://github.com/scottlz0310/spotify-ad-analyzer
cd spotify-ad-analyzer
```

### 2. ディレクトリ作成

```powershell
mkdir shared, data -Force
```

### 3. 環境変数の設定

`.env` ファイルをリポジトリルートに作成（gitignore 済み）：

```env
HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
WHISPER_MODEL=small
OLLAMA_HOST=host.docker.internal:11434
OLLAMA_MODEL=llama3.2
```

または PowerShell セッションに直接設定：

```powershell
$env:HF_TOKEN = "hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

---

## Docker で起動する

### ビルドと起動

```powershell
# イメージビルド + フォアグラウンド起動
docker compose up --build

# バックグラウンド起動
docker compose up -d --build
```

### 起動確認

```
analyzer  | INFO  src.main — spotify-ad-analyzer starting
analyzer  | INFO  src.main — Watching /app/shared — press Ctrl-C to stop
```

### ログ確認・停止

```powershell
docker compose logs -f analyzer   # ログ追従
docker compose down                # 停止
```

---

## 広告 WAV を処理する

`spotify-ad-recorder`（Windows）が `shared/` に書き込んだ WAV ファイルを自動検出します。
手動テストには `tests/fixtures/sample.wav`（0.5 秒無音）を使用できます：

```powershell
$ts = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
Copy-Item tests/fixtures/sample.wav "shared/spotify_ad_$ts.wav"
```

**処理ログの例：**

```
analyzer-1  | INFO  src.watcher — New ad file detected: spotify_ad_20260315_090000.wav
analyzer-1  | INFO  faster_whisper — Processing audio with duration 00:30.000
analyzer-1  | INFO  faster_whisper — Detected language 'ja' with probability 0.95
analyzer-1  | INFO  src.watcher — Pipeline complete: ad_id=1 spotify_ad_20260315_090000.wav
```

> **Note:** Ollama が利用不可の場合は LLM 解析がスキップされ、`WARNING src.pipeline — Ollama unavailable; LLM analysis skipped` が出力されます。パイプラインは正常に完了します。

---

## Web ダッシュボードで解析結果を見る

`docker compose up` を実行するだけでダッシュボードも自動で起動します。

### アクセス

ブラウザで以下の URL を開いてください：

```
http://localhost:8501
```

### ページ構成

| ページ | 内容 |
|--------|------|
| **🎵 トップ（概要）** | 広告総数・文字起こし済み件数・平均時間などのサマリー |
| **📋 広告一覧** | 処理済み WAV ファイルの一覧。ステータス・言語・時間でフィルタリング可能 |
| **🔍 広告詳細** | 選択した広告の文字起こし全文・話者セグメント・LLM 解析結果 |
| **🔊 話者類似度** | Voice Embedding（256-dim）を使った話者間のコサイン類似度マトリクス |

### ダッシュボードのみ起動する場合

```powershell
docker compose up --no-deps dashboard
```

> **Note:** `docker-compose.yml` では `dashboard` が `depends_on: analyzer` を持つため、
> `-d`/`--no-deps` なしで `docker compose up dashboard` を実行すると `analyzer` も起動します。  
> ダッシュボードは `data/ads.db` を含む `data/` ボリュームを読み取り専用（`:ro`）でマウントするため、
> `analyzer` が処理中でも安全に参照できます。

---

## 解析結果を確認する

### DB の内容を確認

```powershell
docker compose exec analyzer python -c "
import sqlite3, json
conn = sqlite3.connect('/app/data/ads.db')
conn.row_factory = sqlite3.Row

print('=== ads ===')
for r in conn.execute('SELECT id, filename, status, error_message FROM ads'):
    print(dict(r))

print('=== transcripts ===')
for r in conn.execute('SELECT ad_id, full_text, language FROM transcripts'):
    print(dict(r))

print('=== llm_analyses ===')
for r in conn.execute('SELECT ad_id, product_name, ad_type, tone FROM llm_analyses'):
    print(dict(r))

print('=== voice_embeddings ===')
for r in conn.execute('SELECT ad_id, speaker, length(embedding) as bytes FROM voice_embeddings'):
    print(dict(r))
"
```

### LLM 解析結果（コンテナ外から）

```powershell
# ads.db をローカルで直接参照
python -c "
import sqlite3
conn = sqlite3.connect('data/ads.db')
conn.row_factory = sqlite3.Row
for r in conn.execute('SELECT * FROM llm_analyses'):
    print(dict(r))
"
```

---

## パターン分析レポートを生成する

`src.pattern_analyzer` CLI を使って集計レポートを JSON で出力します。

### コンテナ内で実行

```powershell
docker compose exec analyzer python -m src.pattern_analyzer report
```

### ローカルで実行（uv）

```powershell
uv run python -m src.pattern_analyzer report --db data/ads.db
```

### オプション

| オプション | デフォルト | 説明 |
|-----------|-----------|------|
| `--db PATH` | `data/ads.db` | SQLite DB ファイルのパス |
| `--threshold FLOAT` | `0.90` | 繰り返し広告判定の cosine 類似度閾値（0.0〜1.0） |

### 出力例

```json
{
  "hourly_frequency": [
    {"hour": 8, "count": 3},
    {"hour": 12, "count": 5}
  ],
  "ad_type_distribution": [
    {"ad_type": "ナレーション", "count": 4, "percentage": 66.67},
    {"ad_type": "音楽", "count": 2, "percentage": 33.33}
  ],
  "tone_distribution": [
    {"tone": "明るい", "count": 5, "percentage": 83.33}
  ],
  "repeat_ad_pairs": [
    {
      "ad_id_a": 1,
      "filename_a": "spotify_ad_2026-03-15_08-00-00.wav",
      "ad_id_b": 3,
      "filename_b": "spotify_ad_2026-03-15_12-00-00.wav",
      "similarity": 0.9823
    }
  ]
}
```

---

## フォルダ内の WAV をまとめて処理する（バッチ処理）

`shared/` を監視する watcher ではなく、すでにフォルダに溜まっている WAV ファイルを
一括処理したい場合は `scripts/process_batch.py` を使います。

### 構文

```
python scripts/process_batch.py <input_dir> <db_path>
```

| 引数 | 説明 |
|------|------|
| `<input_dir>` | `spotify_ad_*.wav` が置かれているディレクトリ |
| `<db_path>` | 結果を保存する SQLite DB ファイルパス（存在しなければ自動作成） |

### コンテナ内で実行する（推奨）

```powershell
# shared/ 内のファイルを処理して data/ads.db に保存
docker compose exec analyzer python scripts/process_batch.py /app/shared /app/data/ads.db

# 別ディレクトリのファイルを別 DB に保存する例
docker compose exec analyzer python scripts/process_batch.py /app/dropbox /app/data/dropbox_ads.db
```

コンテナが起動していない場合は `run` で起動しながら実行できます：

```powershell
docker compose run --rm analyzer python scripts/process_batch.py /app/shared /app/data/ads.db
```

### ローカルで実行する（uv）

```powershell
uv run python scripts/process_batch.py shared data/ads.db
```

### 動作

1. `<input_dir>` から `spotify_ad_*.wav` をファイル名順に列挙する
2. 長尺ファイルはセグメント単位で自動分割（`src/splitter.py`）
3. 各パートに対してフルパイプライン（文字起こし → 話者分離 → 声紋抽出 → LLM 解析）を実行
4. 結果を `<db_path>` の SQLite DB に保存する
5. 処理完了後、一時分割ファイルは自動削除される（元ファイルは変更されない）

### 出力例

```
2026-03-16 10:00:01 INFO batch: Found 5 WAV files in /app/shared
2026-03-16 10:00:01 INFO batch: spotify_ad_2026-03-15_08-00-00.wav  ->  1 part(s): ['spotify_ad_2026-03-15_08-00-00.wav']
2026-03-16 10:00:45 INFO batch:   [OK] ad_id=1  spotify_ad_2026-03-15_08-00-00.wav
2026-03-16 10:01:30 INFO batch:   [OK] ad_id=2  spotify_ad_2026-03-15_09-00-00.wav
...
2026-03-16 10:05:00 INFO batch: Done. Processed 5 parts total -> /app/data/ads.db
```

> **Note:** 処理に失敗したファイルはスキップされ、ログに `[FAIL]` が出力されます。
> 他のファイルの処理は継続されます。

---

## 環境変数リファレンス

| 変数名 | デフォルト値 | 説明 |
|--------|-------------|------|
| `SHARED_DIR` | `/app/shared` | WAV ファイル監視ディレクトリ |
| `DATA_DIR` | `/app/data` | SQLite DB 保存先ディレクトリ |
| `WHISPER_MODEL` | `small` | faster-whisper モデルサイズ（`tiny`/`base`/`small`/`medium`/`large-v3`） |
| `HF_TOKEN` | `""` | Hugging Face アクセストークン（pyannote-audio 必須） |
| `DIARIZE_MODEL` | `pyannote/speaker-diarization-3.1` | 話者分離モデル ID |
| `OLLAMA_HOST` | `host.docker.internal:11434` | Ollama API エンドポイント |
| `OLLAMA_MODEL` | `llama3.2` | Ollama で使用するモデル名 |
| `WATCHDOG_FORCE_POLLING` | `0` | `1` にするとポーリング監視（Docker Desktop / Windows 環境向け） |

---

## トラブルシューティング

| 症状 | 原因候補 | 対処 |
|------|----------|------|
| コンテナが即終了する | 起動エラー | `docker compose logs analyzer` で詳細確認 |
| `diarizer` で認証エラー | HF_TOKEN 不正 / モデル未承認 | トークン確認・HuggingFace でモデル承認 |
| WAV を置いても反応しない | Docker Desktop のファイル監視制限 | `.env` に `WATCHDOG_FORCE_POLLING=1` を追加 |
| LLM 解析がスキップされる | Ollama が起動していない | `ollama serve` で起動・`OLLAMA_HOST` を確認 |
| `status='error'` になる | パイプライン例外 | `SELECT error_message FROM ads WHERE status='error'` で確認 |
| `bytes` が 1024 でない | resemblyzer 初期化失敗 | コンテナログを確認 |
