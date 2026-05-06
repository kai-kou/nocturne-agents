# デモ手順書 — After-Hours Agents

> 審査官・発表者向け。事前準備からフルデモまで 20 分以内で完走できる構成にゃ。

---

## 前提 / Prerequisites

| 項目 | 内容 |
|------|------|
| デプロイ先 | `https://func-aha-dev.azurewebsites.net/api` |
| 確認方法 | `docs/endpoints.md` に最新 URL |
| ツール | `curl` または Postman / REST Client |
| Teams | デモ用 Teams チャンネル（Webhook 設定済み） |
| X API | Bearer Token・OAuth 1.0a 設定済み（省略時は graceful skip） |

---

## シナリオ概要 / Scenario

```
09:30  澪 (Mio-01) が X のポーリングを開始
       └─► SNS ヘルスリスク 87/100 の投稿を検知
           └─► Teams に Adaptive Card 送信
               └─► 担当者が [承認] → X 投稿実行

18:00  砦 (Toride-06) + 読 (Yomi-04) の夜間 Group Chat 起動
       └─► 「今日の対応は楽観的すぎた」と砦が批評
           └─► 「同パターンの炎上が過去 3 件」と読が分析
               └─► 改善アクション 3 件を GitHub PR Draft に

08:00  Morning Digest が Teams に送信
       └─► 担当者が翌朝に PR を確認・マージ承認
```

---

## ⏱️ 5分前チェックリスト / Pre-Demo Checklist

デモ開始 5 分前に以下をすべて確認すること。チェックが外れていたら即座に対処にゃ。

### 環境・接続

- [ ] Azure Functions が起動中であること（ヘルスチェック URL が 200 を返す）
- [ ] Teams デモ用チャンネルが開いていること（Adaptive Card の着信を確認できる状態）
- [ ] GitHub の nocturne-agents リポジトリが開いていること（PR Draft 確認用）
- [ ] Azure Portal の Cosmos DB モニタリングタブが開いていること（任意）

### 環境変数・シークレット

- [ ] `AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_KEY` が設定済み
- [ ] `TEAMS_WEBHOOK_URL` が設定済み（未設定の場合、Morning Digest は skipped になる）
- [ ] `GITHUB_TOKEN` が設定済み（未設定の場合、PR Draft は dry-run になる）
- [ ] X API: 未設定でも graceful skip するため必須ではない（スキップ前提で進行可）

### 動作確認コマンド（コピペで即実行）

```bash
# ヘルスチェック（5秒以内に green が返ることを確認）
curl -s https://func-aha-dev.azurewebsites.net/api/health | jq .status

# デモデータ投入（昼レーンの準備）
curl -s -X POST https://func-aha-dev.azurewebsites.net/api/day/analyze \
  -H "Content-Type: application/json" \
  -d '{"tweet_id":"demo-warmup","text":"テスト","author":"@test","retweet_count":0,"reply_count":0}' \
  | jq .risk_score
```

**判定基準:**

| 結果 | 意味 | 対処 |
|------|------|------|
| `"status": "healthy"` | ✅ OK | そのまま進行 |
| `"status": "degraded"` | ⚠️ 部分障害 | Troubleshooting を確認 |
| タイムアウト / 5xx | ❌ 起動失敗 | Azure Portal でログを確認してにゃ |

---

## Step 1: ヘルスチェック / Health Check (30 秒)

```bash
curl https://func-aha-dev.azurewebsites.net/api/health
```

**期待レスポンス:**

```json
{"status": "healthy", "version": "1.0.0", "agents": ["mio-01", "toride-06", "yomi-04"]}
```

---

## Step 2: 昼レーン デモ / Daytime Lane Demo (5 分)

### 2-1. SNS ヘルスチェック（澪）

```bash
curl -X POST https://func-aha-dev.azurewebsites.net/api/day/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "tweet_id": "demo-20260417-001",
    "text": "弊社サービスの障害について、特に問題ありません。ご不便をおかけして申し訳ありません",
    "author": "@demo_company",
    "retweet_count": 1200,
    "reply_count": 340
  }'
```

**期待レスポンス（ポイント解説）:**

```json
{
  "incident_id": "INC-20260417-001",
  "risk_score": 87,
  "risk_level": "HIGH",
  "triggers": ["楽観的表現: 問題ありません", "エンゲージメント急上昇"],
  "draft_response": "現在調査中です。詳細が判明次第お知らせします。",
  "agent": "mio-01",
  "next_action": "teams_card_sent"
}
```

> ポイント: `risk_score=87` → Teams に Adaptive Card が自動送信されているにゃ

### 2-2. Teams Adaptive Card 確認

デモ用 Teams チャンネルを開き、以下の Card が届いていることを確認:

```
[SNS ヘルスリスク: HIGH 87/100]

投稿: "弊社サービスの障害について、特に問題ありません..."

澪の提案対応文:
「現在調査中です。詳細が判明次第お知らせします。」

[✅ 承認して投稿]  [✏️ 修正して投稿]  [❌ キャンセル]
```

### 2-3. 承認フロー実行（Copilot Studio Webhook）

Teams の **[✅ 承認して投稿]** ボタンを押す（または手動で API を叩く）:

```bash
curl -X POST https://func-aha-dev.azurewebsites.net/api/day/approve \
  -H "Content-Type: application/json" \
  -d '{
    "incident_id": "INC-20260417-001",
    "action": "approved",
    "approved_by": "demo-user"
  }'
```

**期待レスポンス:**

```json
{"status": "posted", "tweet_url": "https://x.com/...", "incident_id": "INC-20260417-001"}
```

---

## Step 3: 夜レーン デモ / Nighttime Lane Demo (8 分)

### 3-1. 夜間 Group Chat 手動起動

```bash
curl -X POST https://func-aha-dev.azurewebsites.net/api/night/nocturne/start \
  -H "Content-Type: application/json"
```

**内部動作（ログで確認）:**

```
[Toride-06] 今日の対応 INC-20260417-001 を批評します。
            "問題ありません"という表現は禁止語です。楽観的すぎた対応でした。
            エスカレーション基準: リスクスコア 87 → 即座に謝罪文に切り替えるべきでした。

[Yomi-04] パターン分類: 「楽観的表現による炎上拡大」
          過去 3 件の類似インシデント: INC-20260301, INC-20260112, INC-20251205
          「同じ火は、同じ場所からまた燃える」
          改善提案: 禁止語リストに「問題ない」を追加

[改善アクション抽出]
  1. persona/mio_01.yaml の禁止語リスト更新
  2. リスクスコア 80+ 時の承認フロー短縮化
  3. 楽観的表現の自動検知ルール強化
```

### 3-2. GitHub PR Draft 確認

```bash
curl https://func-aha-dev.azurewebsites.net/api/night/summary
```

**期待レスポンス:**

```json
{
  "date": "2026-04-17",
  "incidents_reviewed": 1,
  "improvement_actions": 3,
  "pr_draft_url": "https://github.com/kai-kou/kinako-mocchi-hackathon/pull/...",
  "agents": ["toride-06", "yomi-04"]
}
```

GitHub で PR Draft が作成されていることを確認にゃ。

### 3-3. Morning Digest テスト送信

```bash
curl -X POST https://func-aha-dev.azurewebsites.net/api/morning/digest/test
```

Teams の Morning Digest チャンネルに以下が届く:

```
📋 After-Hours Digest — 2026-04-17

昨夜のサマリー:
• 分析インシデント: 1件
• 改善アクション: 3件
• PR Draft: #XX (確認待ち)

[🔗 PR を確認する]
```

---

## Step 4: Cosmos DB データ確認 (オプション / 3 分)

Azure Portal または Azure CLI で Cosmos DB のデータを確認:

```bash
az cosmosdb sql query \
  --account-name cosmos-aha-dev \
  --resource-group rg-after-hours-agents-dev \
  --database-name AfterHoursAgents \
  --container-name shared_core \
  --query "SELECT * FROM c WHERE c.type = 'Incident' ORDER BY c._ts DESC OFFSET 0 LIMIT 5"
```

エージェントの記憶（`Memory` / `AgentKnowledge` タイプ）が蓄積されていることを確認にゃ。

---

## トラブルシューティング / Troubleshooting

| 症状 | 原因 | 対処 |
|------|------|------|
| `401 Unauthorized` | Function キー未設定 | `?code=<function-key>` をクエリに追加 |
| X 投稿がスキップされる | X API 未設定 | `"status": "skipped"` は正常動作（graceful skip） |
| Teams Card が届かない | Webhook URL 未設定 | 環境変数 `TEAMS_WEBHOOK_URL` を確認 |
| Group Chat がタイムアウト | Azure OpenAI 制限 | ルールベースフォールバックが自動起動 |

---

## デモ終了後の確認事項

- [ ] `docs/endpoints.md` に最新 URL が記録されているか
- [ ] Cosmos DB に今日のインシデントデータが保存されているか
- [ ] GitHub に PR Draft が作成されているか
- [ ] Teams の Morning Digest チャンネルにメッセージが届いているか
