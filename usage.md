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
analyzer  | INFO  src.watcher — New ad file detected: spotify_ad_2026-03-15_09-00-00.wav
analyzer  | INFO  src.transcriber — Transcribed: ...
analyzer  | INFO  src.diarizer — Diarized: ...
analyzer  | INFO  src.embedder — Embedded: ...
analyzer  | INFO  src.llm_analyzer — LLM analysis complete
analyzer  | INFO  src.pipeline — Pipeline complete: ad_id=1 status=done
```

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

`src/pattern_analyzer` CLI を使って集計レポートを JSON で出力します。

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
| `blob_len` が 1024 でない | resemblyzer 初期化失敗 | コンテナログの `embedder` 行を確認 |
