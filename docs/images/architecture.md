# アーキテクチャ図 — After-Hours Agents

## システム全体図 (Mermaid)

```mermaid
graph TB
    subgraph "X (Twitter)"
        X_STREAM[X API v2<br/>5分ポーリング]
    end

    subgraph "昼レーン 09:00–18:00"
        MIO[澪 Mio-01<br/>🐦 文鳥<br/>炎上リスク検知]
        SCORE[スコアリング<br/>0–100]
        CARD[Teams<br/>Adaptive Card]
        COPILOT[Copilot Studio<br/>承認フロー]
        TWEET[X 投稿<br/>Tweepy]
    end

    subgraph "夜レーン 18:00–03:00"
        TIMER_N[Timer Trigger<br/>18:00]
        TORIDE[砦 Toride-06<br/>🦝 タヌキ<br/>批評・エスカレーション]
        YOMI[読 Yomi-04<br/>🦉 フクロウ<br/>パターン分析]
        GROUPCHAT[AutoGen<br/>Group Chat]
        PR[GitHub<br/>PR Draft]
    end

    subgraph "Morning 08:00"
        TIMER_M[Timer Trigger<br/>08:00]
        DIGEST[Teams<br/>Morning Digest]
    end

    subgraph "Azure インフラ"
        AF[Azure Functions 1.0<br/>Python 3.11]
        COSMOS[(Cosmos DB<br/>shared_core<br/>private_episodic)]
        ENTRA[Entra Agent ID<br/>RBAC / Managed Identity]
    end

    subgraph "CI/CD"
        GHA[GitHub Actions<br/>OIDC]
    end

    X_STREAM -->|tweet data| MIO
    MIO --> SCORE
    SCORE -->|risk ≥ 50| CARD
    CARD --> COPILOT
    COPILOT -->|承認| TWEET
    COPILOT -->|キャンセル| COSMOS

    TIMER_N --> GROUPCHAT
    TORIDE --> GROUPCHAT
    YOMI --> GROUPCHAT
    GROUPCHAT --> PR
    GROUPCHAT --> COSMOS

    TIMER_M --> DIGEST

    MIO <--> COSMOS
    TORIDE <--> COSMOS
    YOMI <--> COSMOS

    AF --- MIO
    AF --- TORIDE
    AF --- YOMI
    ENTRA -.->|権限制御| AF

    GHA -->|deploy| AF
```

## コンポーネント説明

### エージェント

| エージェント | 役割 | AutoGen 型 | 記憶タイプ |
|------------|------|-----------|----------|
| 澪 (Mio-01) | X 監視・リスクスコアリング・対応案生成 | `AssistantAgent` | `Incident`, `Memory` |
| 砦 (Toride-06) | 対応批評・エスカレーション判断 | `AssistantAgent` | `Memory`, `AgentKnowledge` |
| 読 (Yomi-04) | パターン分類・類似インシデント検索 | `AssistantAgent` | `AgentKnowledge` |

### データフロー

```
Incident 作成 (澪)
    │
    ├── shared_core コンテナ
    │   └── type: "Incident" — 全エージェント共有
    │
    └── private_episodic コンテナ
        ├── type: "Memory"        — 各エージェントの記憶
        └── type: "AgentKnowledge" — 蓄積された知識
```

### Human-in-the-loop ポイント

```
昼: Adaptive Card → [承認/修正/キャンセル] → X 投稿
夜: PR Draft 作成 → 翌朝レビュー → マージ承認
```

AI は **提案まで** 。実行は必ず人間が承認する。

## Persona Card YAML 構造

```yaml
# personas/mio_01.yaml
agent_id: mio-01
name: 澪
species: 文鳥
shift: daytime
persona:
  business_mode:
    tone: "冷静・データドリブン"
    forbidden_words: ["大丈夫", "問題ない", "きっと"]
  casual_mode:
    tone: "親しみやすい・わかりやすい"
scoring:
  high_threshold: 80
  medium_threshold: 50
```

## セキュリティ設計

| 項目 | 設計 |
|------|------|
| 認証 | Entra Agent ID (Managed Identity) — シークレット不使用 |
| 権限 | RBAC 最小権限 (Cosmos DB 読取/書込のみ) |
| CI/CD | GitHub Actions OIDC (Workload Identity Federation) |
| Secrets | Azure Functions Application Settings (暗号化) |
