# Copilot Instructions — spotify-ad-analyzer

## プロジェクト概要

`spotify-ad-recorder`（C# / Windows）が録音した Spotify 広告 WAV ファイルを
自動検出し、文字起こし・話者分離・声紋抽出・LLM 解析まで行う解析パイプライン。

| 項目 | 内容 |
|------|------|
| 言語 | Python 3.12 |
| パッケージ管理 | **uv**（ロックファイル: `uv.lock`） |
| 実行環境 | Docker（Linux コンテナ）|
| GPU | **CPU 専用**（CUDA 非対応） |
| DB | SQLite（`data/ads.db`） |
| LLM | ローカル LLM（Ollama）、オフライン実行 |

---

## ローカル開発セットアップ（uv）

```bash
# 仮想環境作成 + 依存関係インストール（初回）
uv sync --all-groups

# pre-commit フック登録（初回のみ）
uv run pre-commit install

# パッケージ追加
uv add <package>
uv add --group dev <package>   # 開発依存
```

---

## ビルド・実行

```bash
# イメージビルド + コンテナ起動
docker compose up --build

# バックグラウンド起動
docker compose up -d --build

# ログ確認
docker compose logs -f analyzer

# コンテナ停止
docker compose down
```

---

## テスト

```bash
# テスト全体（並列 + カバレッジ）
uv run pytest -n auto --cov=src --cov-report=term-missing

# 単一テストファイル
uv run pytest tests/test_transcriber.py -v

# 単一テスト関数
uv run pytest tests/test_pipeline.py::test_full_pipeline -v

# Docker 内で実行
docker compose run --rm analyzer pytest -n auto --cov=src
```

---

## Lint / Format / Typecheck

```bash
# Format（自動修正）
uv run ruff format .

# Lint（自動修正）
uv run ruff check . --fix

# Lint チェックのみ（修正なし）
uv run ruff check .

# 型チェック
uv run basedpyright

# pre-commit（全フック実行）
uv run pre-commit run --all-files
```

---

## アーキテクチャ

```
shared/spotify_ad_*.wav  ← spotify-ad-recorder（Windows）が書き込む
        │
        ▼ watcher.py (watchdog)
        │
        ▼ pipeline.py ─────────────────────────────────────
        ├── transcriber.py   (faster-whisper)  → セグメント+テキスト
        ├── diarizer.py      (pyannote-audio)  → 話者ラベル
        ├── embedder.py      (resemblyzer)     → Voice Embedding (256-dim)
        ├── db.py            (SQLite)          → data/ads.db へ保存
        ├── llm_analyzer.py  (Ollama REST)     → 広告解析テキスト [Phase 3]
        └── pattern_analyzer.py (SQL 集計)     → パターンレポート [Phase 4]
```

### モジュール責務

| ファイル | 責務 |
|---------|------|
| `src/main.py` | エントリポイント。watcher 起動・SIGINT/SIGTERM ハンドリング |
| `src/watcher.py` | `shared/` を watchdog で監視。新規 `.wav` を pipeline へ渡す |
| `src/pipeline.py` | transcriber/diarizer/embedder を呼び出し、DB へ保存するオーケストレーター |
| `src/transcriber.py` | faster-whisper ラッパー。モデルサイズは環境変数 `WHISPER_MODEL` |
| `src/diarizer.py` | pyannote-audio 3.x ラッパー |
| `src/embedder.py` | resemblyzer ラッパー。embedding を numpy float32 BLOB で保存 |
| `src/db.py` | SQLite スキーマ定義・CRUD ヘルパー |
| `src/llm_analyzer.py` | Ollama REST API クライアント（Phase 3） |
| `src/pattern_analyzer.py` | SQL 集計クエリ・CLI レポート（Phase 4） |

---

## 連携インターフェース（recorder との契約）

```
ファイル名形式: spotify_ad_yyyy-MM-dd_HH-mm-ss.wav
例:             spotify_ad_2026-03-08_21-33-05.wav
```

**これが両リポジトリ間の唯一の境界面。** ファイル名規則を変更してはならない。

---

## SQLite スキーマ（`data/ads.db`）

```sql
ads             -- WAV ファイルごとのメタデータ（status: pending/processing/done/error）
segments        -- 話者×テキスト×時間範囲（ad_id FK）
transcripts     -- 全文テキスト・言語・Whisperモデル（ad_id PK）
voice_embeddings -- 話者ごとの 256-dim embedding BLOB（ad_id FK）
llm_analyses    -- Ollama 解析結果（商品名・広告種別・要約・トーン）（Phase 3）
```

---

## 環境変数

| 変数 | デフォルト | 説明 |
|------|-----------|------|
| `SHARED_DIR` | `/app/shared` | WAV ファイル監視ディレクトリ |
| `DATA_DIR` | `/app/data` | SQLite DB 保存先 |
| `WHISPER_MODEL` | `small` | tiny / base / small / medium |
| `OLLAMA_HOST` | `host.docker.internal:11434` | Ollama エンドポイント（Phase 3） |

---

## ツール設定（pyproject.toml 抜粋）

### ruff — lint & format

```toml
[tool.ruff]
target-version = "py312"
line-length = 88

[tool.ruff.lint]
select = ["ALL"]
ignore = [
    "D",      # pydocstyle（docstring は任意）
    "ANN101", # self の型注釈不要
    "COM812", # formatter と競合
]

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["S101"]  # assert 許可
```

### basedpyright — 型チェック（最厳格）

```toml
[tool.basedpyright]
pythonVersion = "3.12"
typeCheckingMode = "all"       # strict + 追加チェック全有効
reportAny = true               # Any 型を明示的エラーとする
reportUnknownVariableType = true
reportUnknownMemberType = true
```

### pytest

```toml
[tool.pytest.ini_options]
addopts = "-n auto --cov=src --cov-report=term-missing --cov-fail-under=80"
testpaths = ["tests"]

[tool.coverage.run]
branch = true
source = ["src"]
```

### pre-commit（`.pre-commit-config.yaml`）

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    hooks:
      - id: ruff-format
      - id: ruff
        args: [--fix]
  - repo: https://github.com/RobertCraigie/pre-commit-hooks-basedpyright
    hooks:
      - id: basedpyright
```

---

## 実装規約

### 型安全

- **すべての関数・メソッドに型注釈必須**（引数・戻り値）
- `Any` 型は原則使用禁止。外部ライブラリの型スタブが不完全な場合は `cast()` または `TypeVar` で対処
- `Optional[X]` より `X | None` を使う（Python 3.10+ スタイル）
- numpy array の型は `npt.NDArray[np.float32]` 等で明示
- 辞書の代わりに `TypedDict` または `dataclass` を使う

### コード構造

- `src/` 配下にモジュールを配置し `src/__init__.py` を置く
- 各モジュールは単一責務（transcriber は transcribe のみ）
- 環境変数は `src/config.py` で一元管理し、他モジュールから直接 `os.environ` を読まない
- SQLite 操作はすべて `db.py` 経由に集約する
- `shared/` と `data/` と `uv.lock` を除く生成物は `.gitignore` で除外する

### やらないこと

- GPU / CUDA 依存のコードを追加しない
- `# type: ignore` コメントは使わない（型スタブ整備か `cast()` で対処）
- Spotify Web API・OAuth 認証は使わない
- クラウド LLM API（OpenAI / Anthropic）は使わない
- ファイル名規則（`spotify_ad_*.wav`）を変更しない

---

## Git ワークフロー

**1タスク = 1 PR。** `tasks.md` の各タスクが 1 つの PR に対応する。

### PR サイクル

```
1. feat/<topic> ブランチを main から作成
2. 実装 + テスト（ruff / basedpyright / pytest をパスすること）
3. PR を作成（タイトル: "feat: <内容>"）
4. GitHub Copilot による自動レビューを依頼
5. レビューコメントをすべて解決してから再レビュー依頼
6. 承認後に Squash merge → main
7. tasks.md の該当タスクを [x] に更新し、完了セクションへ移動
```

### ブランチ命名

| 種別 | 形式 | 例 |
|------|------|----|
| 機能追加 | `feat/<topic>` | `feat/transcriber` |
| バグ修正 | `fix/<topic>` | `fix/watcher-race-condition` |
| ドキュメント | `docs/<topic>` | `docs/readme` |
| 依存関係更新 | Renovate が自動作成 | — |

### PR の粒度ルール

- 1 PR でレビュアーが 30 分以内に理解できる変更量にする
- 新機能は必ずテストを同じ PR に含める
- `main` への直接プッシュは行わない
