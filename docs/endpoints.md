# After-Hours Agents — デプロイ済みエンドポイント

> このファイルは `scripts/deploy.sh` によって自動更新されます。
> デプロイ前は URL が未確定のためプレースホルダーが表示されます。

## デプロイ状態

| 項目 | 値 |
|------|---|
| 最終デプロイ | （未デプロイ）|
| 環境 | dev |
| Function App | `func-aha-dev` |
| ベース URL | `https://func-aha-dev.azurewebsites.net/api` |

## ヘルスチェック

```
GET https://func-aha-dev.azurewebsites.net/api/health
```

## 昼レーン（Daytime Lane）

| メソッド | パス | 説明 |
|---------|------|------|
| POST | `/api/day/analyze` | 澪による手動分析（デバッグ用）|
| POST | `/api/day/send-card` | Teams Adaptive Card 送信 |
| POST | `/api/day/approve` | Copilot Studio 承認 Webhook |
| GET  | `/api/day/incidents` | インシデント一覧取得 |

## 夜レーン（Nighttime Lane）

| メソッド | パス | 説明 |
|---------|------|------|
| POST | `/api/night/nocturne/start` | 夜間 Group Chat 手動起動 |
| POST | `/api/night/pr-draft` | GitHub PR Draft 作成 |
| GET  | `/api/night/summary` | 最新振り返りサマリー取得 |
| POST | `/api/morning/digest/test` | Morning Digest 手動送信 |

## ハッカソン提出用 URL

```
https://func-aha-dev.azurewebsites.net/api/health
```

> ⚠️ デプロイ後に `scripts/deploy.sh` を実行すると、実際の URL に自動更新されます。
