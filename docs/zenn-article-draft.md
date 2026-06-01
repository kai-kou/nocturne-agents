---
title: "おはようございます、昨夜の失敗、直しておきました。— AI 放課後エージェントが自律的に働く夜の話"
emoji: "🌙"
type: "tech"
topics: ["azure", "agentframework", "copilot", "llm", "python"]
published: false
---

# おはようございます、昨夜の失敗、直しておきました。

> 「AI たちも、休む。だから引き継ぐ。引き継ぎが会議になり、昨日の失敗が今日の改善になる。」

---

## この記事について

Microsoft Agent Hackathon 2026 への提出作品「 **AI 放課後 / After-Hours Agents** 」の技術解説記事です。

SNS 炎上対応を自動化する AI エージェント群が、 **昼は発信トーン分析・対応** し、 **夜は自律的に集まって振り返り** を行い、翌朝には改善案（GitHub PR）を人間の出社前に用意しておく——そんなシステムを Azure AI Foundry × AutoGen × Copilot Studio で実装しました。

---

## プロダクトの全体像

### コンセプト：シフト制 AI と自律的な夜の会議

従来の炎上対応 AI は 24 時間休まず稼働し、均質な判断を繰り返します。私たちは逆を選びました。

**人間と同じシフト制を採用し、AI にも「休み」と「引き継ぎ」を与えました。**

8 体のエージェントは世代・専門領域・コミュニケーションスタイルを意図的にバラバラに設計しています。均質な AI が見落とす「機微」を、感知できる角度の違いが拾い上げる。持続可能な AI は、休み・繋がり・学ぶ。

### なぜ 24 時間均質 AI では不十分か

「24 時間休まず稼働する AI の方が炎上には強いのでは？」——この当然の問いへの答えが、シフト制採用の核心です。

**文脈は蓄積されないと消える。** 炎上対応は「今日の判断」が「昨日の判断」の文脈で変わります。多くの AI システムでは 24 時間稼働していても各リクエストが独立処理され、引き継ぎが発生しません。シフト制は **引き継ぎを強制** します。その引き継ぎが会話になり、昨日の失敗が今日の改善につながる。

**感知角度の多様性が内輪の合理化を防ぐ。** 夜勤の砦が昼勤の判断に反論できるのは、担当が変わるからです。同じエージェントが同じ文脈で判断し続けると、閾値が徐々にずれていきます。砦の口癖「反論できない対応は次の炎上の種」は、この構造的リスクへの処方箋です。

**最終判断は人間が担う（Human-in-the-loop）。** AI は「夜通し準備し、翌朝に人間が承認する」フローに徹します。炎上対応のような高感度業務において、最終判断を AI に委ねない設計だからこそシフト制が合う。シフトの切れ目が「人間確認のタイミング」になるのです。

1 時間ポーリング（720 リクエスト/月）により、重大リスクワードを含む投稿を定期検知します。デモ時は HTTP エンドポイントによる即時トリガーも可能です（X API Pay-Per-Use・詳細はシステムアーキテクチャを参照）。

### 看板エージェント 3 体

| エージェント | 動物 | 担当 | キャラクター |
|------------|------|------|------------|
| **澪（Mio-01）** | 文鳥 🐦 | 炎上予測・昼番 | 「この投稿、3時間後に燃えます」|
| **砦（Toride-06）** | タヌキ 🦝 | 反論・クリティカル・夜番 | 「反論できない対応は次の炎上の種」|
| **読（Yomi-04）** | フクロウ 🦉 | パターン分析・夜番 | 「同じ火は、同じ場所からまた燃える」|

読は飲み会に参加しません。議事録だけ送ってきます。

---

## システムアーキテクチャ

### 昼レーン（Daytime Lane）

```
Azure Functions Timer Trigger（cron: 毎時 = 1 時間ポーリング）
  └→ 澪（Mio-01）: AutoGen AssistantAgent
      ├─ ルールベーススコアリング（リスクスコア 0-100）
      ├─ LLM 分析（Azure OpenAI gpt-4o-mini）
      └─ 閾値超過時 → Cosmos DB にインシデント記録
          └→ Copilot Studio: Adaptive Card 送信
              ├─ [承認] → X API で対応投稿を実行
              ├─ [修正] → 修正テキストで投稿
              └─ [キャンセル] → クローズ記録
```

**Human-in-the-loop** の設計原則として、AI が提案し人間が最終判断する構造を徹底しています。炎上対応のような高感度業務において、AI の完全自律化ではなく「AI が夜通し準備し、人間が出社して承認する」フローが最適だと考えました。

### 夜レーン（Nighttime Lane）

```
Azure Functions Timer Trigger（cron: UTC 14:00 = JST 23:00）
  └→ Cosmos DB から本日のインシデント取得
      └→ RoundRobinGroupChat（AutoGen v0.4）
          ├─ 砦（Toride-06）: 「この対応、反論できますか？」クリティカル分析
          ├─ 読（Yomi-04）: 「過去に同じパターンがあります」パターン分析
          └─ MaxMessageTermination（4ターン）で自動終了
              └→ 振り返りサマリー → GitHub PR Draft 自動作成
                  （ai-draft / nocturne / needs-human-review ラベル）

Azure Functions Timer Trigger（cron: UTC 23:00 = JST 翌 08:00）
  └→ Teams Morning Digest Adaptive Card 送信
      └→ 担当者が出社前に確認 → PR マージ承認
```

---

## 実装詳細

### Persona Card YAML

各エージェントの人格・権限・動作モードを YAML で定義しています。

```yaml
persona_id: "Toride-06"
display_name:
  ja: "砦"
  en: "Toride"

base_persona:
  type: "hybrid"  # kinako 60% / mochi 20% / neko 20%
  traits:
    - name: "クリティカル思考"
      description: "反論できない対応案を見つけるまで指摘し続ける"
  animal:
    species: "タヌキ"
    emoji: "🦝"
  shift: "night"

mode:
  business:
    tone: "critical"
    forbidden_words: ["問題ない", "大丈夫"]  # 楽観的表現は禁止語

permissions:
  tools_allowed:
    - "cosmos_shared_read"
    - "cosmos_shared_write"
    - "github_pr_draft_create"
  identity:
    entra_agent_id_env: "ENTRA_AGENT_ID_TORIDE_06"
```

Persona Card は **装飾ではなく、ランタイムでシステムプロンプトを動的生成します** 。 `persona_loader.py` の `build_character_header()` が YAML から口癖・特性・禁止語を組み立て、各 `agent.py` の `_build_system_prompt()` に渡します。 `tools_allowed` フィールドは `_build_agent_tools()` で FunctionTool に変換され、エージェントが実際に呼べるツールを制御します。

また **ビジネスモードとカジュアルモードの 2 モード** を持ちます。昼間の業務分析は structured JSON 出力、夜の Group Chat では会話形式に切り替わります。

### 炎上リスクスコアリング（澪の判断ロジック）

ルールベースのスコアリングに LLM 分析を重ねる 2 段階設計です。

```python
_RISK_WEIGHTS: dict[str, float] = {
    "不買運動": 25,
    "訴訟": 25,
    "謝罪": 20,
    "差別": 20,
    "パワハラ": 20,
    # ... 計 13 キーワード
}

def calculate_risk_score(text: str, engagement_metrics: dict | None = None) -> tuple[float, list[str]]:
    matched: list[str] = [kw for kw in _RISK_WEIGHTS if kw in text]
    score = sum(_RISK_WEIGHTS[kw] for kw in matched)
    if engagement_metrics:
        rt = engagement_metrics.get("retweet_count", 0)
        score += min(rt * 0.1, 30.0)  # エンゲージメント補正（上限 30）
    return min(score, 100.0), matched
```

LLM 接続が失敗した場合でも、ルールベースにフォールバックして動作継続します。「AI が壊れたから対応できない」が起きない設計です。

### 夜の Group Chat 実装（AutoGen RoundRobinGroupChat）

砦と読の 2 エージェントが AutoGen `RoundRobinGroupChat` で今日のインシデントを共同レビューします。

```python
from typing import Any
from autogen_agentchat.conditions import MaxMessageTermination
from autogen_agentchat.teams import RoundRobinGroupChat

async def _run_nocturne_group_chat(incidents: list[dict[str, Any]]) -> dict[str, Any]:
    team = RoundRobinGroupChat(
        participants=[get_toride_agent(), get_yomi_agent()],
        termination_condition=MaxMessageTermination(max_messages=4),
    )
    task_result = await team.run(task=_build_nocturne_prompt(incidents))

    messages = getattr(task_result, "messages", [])
    toride_msgs = [m for m in messages if getattr(m, "source", "") == "Toride_06"]
    yomi_msgs   = [m for m in messages if getattr(m, "source", "") == "Yomi_04"]

    return {
        "escalation_count": ...,   # 砦が「要エスカレーション」と判断した件数
        "yomi_patterns": [...],    # 読が検出した過去パターン一覧
        "actions": [...],          # 改善アクション（最大 5 件）
        "group_chat_messages": len(messages),
    }
```

**4 ターンで自動終了** （`MaxMessageTermination`）するため、コスト・時間が予測可能です。

### GitHub PR Draft 自動生成

夜の合議結果は翌朝の GitHub PR Draft として自動生成されます。

```markdown
## 夜間振り返りサマリー
**日時**: 2026-04-17 23:00 JST

## 本日のインシデント実績
| インシデントID | リスクスコア | 人間の判断 | 結果 |
| incident_abc123 | 85 | approved | 公式謝罪を実施 |

## 砦（Toride-06）の指摘
「様子を見る」という対応案は即時対応の遅れがリスクになります

## 読（Yomi-04）のパターン分析
「品質問題」パターンの過去インシデント: 3 件。同じ火は、同じ場所からまた燃える。

## ⚠️ Human-in-the-loop 確認事項
- [ ] 提案アクションは業務ポリシーに沿っているか
```

PR には `ai-draft` / `nocturne` / `needs-human-review` ラベルが自動付与されます。人間がマージを承認するまで変更は反映されません。

---

## 技術スタック

| 層 | 技術 | 役割 |
|---|------|------|
| エージェント | AutoGen v0.4（autogen-agentchat・Microsoft 開発）| マルチエージェント協調・RoundRobinGroupChat |
| バックエンド | Azure Functions 1.0（Python） | HTTP / Timer Trigger |
| データ | Azure Cosmos DB | shared_core + private_episodic |
| オーケストレーション | Copilot Studio + Power Automate | Scheduled Prompts・承認 Adaptive Card |
| SNS | X API v2（Pay-Per-Use） | 投稿監視・実投稿 |
| 認証 | Microsoft Entra Agent ID（Managed Identity） | エージェント別権限分離（Cosmos DB の読み書きをエージェント単位で制御）|
| メッセージング | Teams Adaptive Card v1.5 | Morning Digest・承認フロー |
| CI/CD | GitHub Actions（OIDC） | テスト・デプロイ |

### X API コスト試算

| 項目 | 試算値 |
|------|--------|
| 検索 API（1 時間ポーリング） | 720 リクエスト/月 |
| Pay-Per-Use 単価（Owned reads・OAuth 1.0a） | **$0.001 / リクエスト** |
| 月額概算 | **$0.72〜** |

X API 2026 年 4 月改定の Owned reads 単価 $0.001/req を適用しています。
OAuth 1.0a で自アカウント投稿を監視する場合は一般 reads（$0.005/req）の 1/5 のコストになります。

---

## デモシナリオ

1. **監視開始**: X API が炎上リスクワード「不買運動」を含む投稿を検出
2. **澪が分析**: リスクスコア 85 → インシデント登録 → Teams に Adaptive Card 送信
3. **人間が承認**: Copilot Studio 経由で「承認」ボタンをクリック
4. **澪が投稿**: X API で公式コメントを自動投稿
5. **23:00 夜の会議**: 砦が「様子を見る」対応を批評 → 読がパターンを分類
6. **GitHub PR 自動生成**: 「炎上予測スコア閾値を 70→60 に引き下げ」の改善案
7. **翌朝 8:00**: Teams に Morning Digest 到着 → 担当者が出社前に確認
8. **PR マージ承認**: 人間が内容確認して merge → 改善が反映

---

## 設計のこだわり：なぜシフト制か

AI を 24 時間単一インスタンスで稼働させると 3 つの問題が生じます：

1. **疲弊なき判断の均質化** — 同じ閾値で同じ判断を繰り返し、文脈変化に鈍感になる
2. **振り返りの欠如** — 今日の判断が明日に活きない
3. **単一観点の脆弱性** — 1 体のエージェントが見落とすものを誰も補完しない

シフト制は「引き継ぎ」を強制します。引き継ぎが会話になり、会話がナレッジになる。 **AI の学習を「学習フェーズ」から切り離し、業務の中に埋め込む** のが After-Hours Agents の核心です。

---

## ハーネスエンジニアリング

After-Hours Agents の実装品質を支えるのは、炎上対応エージェント本体だけではありません。 **AI 自身の暴走を物理的に防ぐ「ハーネス」** を段階的に組み込んでいます。

本プロジェクトでは、AI エージェントの品質をコードで物理的に担保する「ハーネスエンジニアリング」を実践しています。

| レベル | 形態 | 実装例 |
|-------|------|--------|
| Lv1 | ドキュメント | CLAUDE.md、Persona Card YAML |
| Lv2 | AI セマンティックチェック | self-reviewer スキル（並列サブエージェント）|
| Lv3 | ハーネスフック（物理ブロック） | pre-git-push、pre-pr-create スクリプト |
| Lv4 | CI | GitHub Actions（Gemini + Copilot 並列レビュー・テスト自動実行）|

**「ルールを守らないと物理的に進めない」制約を段階的に組み込む** ことで、AI が暴走せずに人間の監督下で動く設計を実現しています。

---

## まとめ

- 🌙 **夜の自律合議** — AI が夜中に反省会を開いて改善案を作る
- ☀️ **朝の人間承認** — 出社したら改善案が PR になって待っている
- 🎭 **シフト制エージェント** — 均質でない AI が均質でない炎上を捉える
- 🔒 **Human-in-the-loop 徹底** — AI は提案し、人間が決める

> **「Agentic AI は、業務を奪うのではなく、夜を豊かにする。」**

---

## リポジトリ

- GitHub: [kai-kou/nocturne-agents](https://github.com/kai-kou/nocturne-agents)（審査時 public 公開予定）
- 実装言語: Python 3.11
- テスト: pytest 73 件 PASS（nocturne-agents product tests）+ 481 件（harness tooling tests）= **554 件合計**

---

*Microsoft Agent Hackathon 2026 提出作品*
