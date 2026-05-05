# After-Hours Agents — AI 放課後 / 夜間自律エージェント

> **"おはようございます、昨夜の失敗、直しておきました。"**

Microsoft Agent Hackathon 2026 提出プロダクト。
提出用リポジトリ: [`kai-kou/nocturne-agents`](https://github.com/kai-kou/nocturne-agents)

SNS ヘルスチェックを **昼は AI が検知・提案、夜は AI が反省・改善** するシフト制マルチエージェントシステム。
Human-in-the-loop 設計により、AI は **提案まで** を担当し、実行は必ず人間が承認する。

---

## プロダクト概要 / Product Overview

**日本語**: X（旧 Twitter）で SNS ヘルスリスクの高い投稿を検知し、専門エージェント 3 体が連携して発信トーン改善案を作成。
夜間は自律的に振り返り Group Chat を行い、翌朝に改善 PR を自動作成する。

**English**: A multi-agent system that monitors X (Twitter) for communication health risks, coordinates three specialized
agents to draft responses, and autonomously runs overnight retrospectives to create improvement PRs by morning.

---

## 看板 3 体 / Core Agents

| # | 和名 | 英名 | 動物 | キャッチフレーズ | シフト |
|---|------|------|------|----------------|--------|
| Mio-01 | **澪** | Mio | 文鳥 🐦 | 「この投稿、3時間後に燃えます」 | 日勤 09:00–18:00 |
| Toride-06 | **砦** | Toride | タヌキ 🦝 | 「反論できない対応は次の炎上の種」 | 夜勤 18:00–03:00 |
| Yomi-04 | **読** | Yomi | フクロウ 🦉 | 「同じ火は、同じ場所からまた燃える」 | 夜勤 18:00–03:00 |

---

## アーキテクチャ / Architecture

```
┌─────────────────── 昼レーン (Daytime Lane) ────────────────────┐
│                                                                  │
│  X API ──5分ポーリング──► 澪 (Mio-01)                           │
│                           │ スコアリング                         │
│                           ▼                                      │
│                   Adaptive Card 送信                             │
│                           │                                      │
│                    ┌──────┴──────┐                               │
│                    ▼             ▼                               │
│               [承認] ──── Copilot Studio ──── [修正/キャンセル]  │
│                    │                                             │
│                    ▼                                             │
│              X 投稿実行 (Tweepy)                                 │
└──────────────────────────────────────────────────────────────────┘

┌─────────────────── 夜レーン (Nighttime Lane) ───────────────────┐
│                                                                  │
│  18:00 Timer ──► 砦 (Toride-06) ──┐                             │
│                                    ├─► AutoGen Group Chat        │
│                  読 (Yomi-04) ────┘         │                    │
│                                             ▼                    │
│                                    改善アクション抽出             │
│                                             │                    │
│                                  GitHub PR Draft 作成             │
│                                             │                    │
│  08:00 Morning ──────────────── Teams Digest 送信                │
│  Digest Timer                               │                    │
│                                      人間がレビュー              │
│                                      & マージ承認               │
└──────────────────────────────────────────────────────────────────┘

共通インフラ:
  Azure Functions 1.0 (Python) + Cosmos DB + Entra Agent ID (RBAC)
```

詳細アーキテクチャ図は [`docs/images/architecture.md`](docs/images/architecture.md) を参照にゃ。

---

## 技術スタック / Tech Stack

| レイヤー | 採用技術 |
|---------|---------|
| エージェント基盤 | AutoGen 0.4.9 (`AssistantAgent` + `GroupChat`) |
| ホスティング | Azure Functions 1.0 (Python 3.11, Consumption Plan) |
| データ永続化 | Azure Cosmos DB for NoSQL |
| 認証・権限管理 | Entra Agent ID + Managed Identity (RBAC) |
| 人間承認フロー | Microsoft Teams Adaptive Card + Copilot Studio |
| SNS 連携 | X API v2 (Tweepy) |
| CI/CD | GitHub Actions + OIDC (シークレット不要) |
| テスト | pytest + pytest-asyncio |

---

## セットアップ / Setup

### 前提条件 / Prerequisites

- Python 3.11+
- Azure Functions Core Tools v4
- Azure CLI (`az login` 済み)
- X API v2 認証情報（Bearer Token + OAuth 1.0a）

### ローカル起動 / Local Start

```bash
# 1. 依存インストール
pip install -r src/requirements.txt

# 2. 設定ファイル生成（Azure リソースが必要）
bash scripts/provision.sh dev

# 3. ローカル起動
cd src && func start

# 4. ヘルスチェック
curl http://localhost:7071/api/health
```

### テスト / Testing

```bash
cd src && python -m pytest tests/unit/ -v
```

---

## API エンドポイント / Endpoints

デプロイ後は [`docs/endpoints.md`](docs/endpoints.md) を参照にゃ。

| Method | Path | 説明 / Description |
|--------|------|--------------------|
| GET | `/api/health` | ヘルスチェック |
| POST | `/api/day/analyze` | 澪による手動分析 |
| POST | `/api/day/approve` | Copilot Studio 承認 Webhook |
| POST | `/api/night/nocturne/start` | 夜間 Group Chat 手動起動 |
| POST | `/api/night/pr-draft` | GitHub PR Draft 作成 |
| POST | `/api/morning/digest/test` | Morning Digest 手動送信 |

---

## デモ手順 / Demo Guide

詳細は [`docs/demo-guide.md`](docs/demo-guide.md) を参照にゃ。

### クイックデモ (5 分) / Quick Demo

```bash
# 1. 昼レーン: SNS ヘルスチェック
curl -X POST https://func-aha-dev.azurewebsites.net/api/day/analyze \
  -H "Content-Type: application/json" \
  -d '{"tweet_id": "demo-001", "text": "テスト投稿"}'

# 2. 夜レーン: Group Chat 手動起動
curl -X POST https://func-aha-dev.azurewebsites.net/api/night/nocturne/start

# 3. Morning Digest 確認
curl -X POST https://func-aha-dev.azurewebsites.net/api/morning/digest/test
```

---

## ディレクトリ構成 / Directory Structure

```
kinako-mocchi-hackathon/
├── src/
│   ├── agents/
│   │   ├── mio_01/         # 澪: SNS ヘルスチェック・対応案生成
│   │   ├── toride_06/      # 砦: 批評・エスカレーション判断
│   │   └── yomi_04/        # 読: パターン分類・知識蓄積
│   ├── blueprints/
│   │   ├── day_lane.py     # 昼レーン (X ポーリング・承認フロー)
│   │   └── night_lane.py   # 夜レーン (Group Chat・PR Draft・Morning Digest)
│   ├── personas/           # Persona Card YAML (各エージェント人格定義)
│   ├── shared/             # Cosmos DB クライアント・Pydantic モデル
│   └── tests/unit/         # pytest ユニットテスト
├── scripts/
│   ├── provision.sh        # Azure リソース自動プロビジョニング
│   ├── deploy.sh           # Azure Functions デプロイ
│   └── azure-auth.sh       # Azure 認証ヘルパー
├── docs/
│   ├── endpoints.md        # デプロイ済み URL 一覧
│   ├── demo-guide.md       # デモ手順書
│   ├── zenn-article-draft.md  # Zenn 記事ドラフト
│   └── images/             # アーキテクチャ図
└── .github/workflows/      # CI/CD (provision / deploy)
```

---

## ライセンス / License

Apache-2.0

---

## 関連リンク / Links

- [Zenn 記事](docs/zenn-article-draft.md) — ハッカソン必須提出物
- [デモ手順書](docs/demo-guide.md)
- [エンドポイント一覧](docs/endpoints.md)
- [MVP 設計書](docs/mvp-design.md)
- 提出用リポジトリ: `kai-kou/nocturne-agents`
