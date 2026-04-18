#!/usr/bin/env bash
# scripts/deploy.sh — After-Hours Agents Azure Functions デプロイ
#
# 前提:
#   - az login 済み（または scripts/azure-auth.sh で認証済み）
#   - func CLI（Azure Functions Core Tools v4）インストール済み
#   - src/local.settings.json が存在する（provision.sh で自動生成）
#
# 使い方:
#   bash scripts/deploy.sh [dev|prod]

set -euo pipefail

ENV="${1:-dev}"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_DIR="${PROJECT_ROOT}/src"
ENDPOINTS_FILE="${PROJECT_ROOT}/docs/endpoints.md"

SUFFIX="aha-${ENV}"
FUNC_APP_NAME="func-${SUFFIX}"
RG_NAME="rg-after-hours-agents-${ENV}"

echo "=== After-Hours Agents デプロイ開始 ==="
echo "  環境             : ${ENV}"
echo "  Function App 名  : ${FUNC_APP_NAME}"
echo "  リソースグループ : ${RG_NAME}"
echo ""

# ---- Step 0: Azure 認証確認 ----
if ! az account show &>/dev/null; then
  echo "  Azure 未認証のため自動認証を試みるにゃ..."
  bash "${PROJECT_ROOT}/scripts/azure-auth.sh"
fi

SUBSCRIPTION=$(az account show --query id -o tsv)
echo "✅ サブスクリプション: ${SUBSCRIPTION}"

# ---- Step 1: Python 依存パッケージインストール ----
echo ""
echo "--- Step 1: 依存パッケージインストール ---"
pip install -r "${SRC_DIR}/requirements.txt" --quiet
echo "✅ requirements.txt インストール完了"

# ---- Step 2: Azure Functions デプロイ ----
echo ""
echo "--- Step 2: Azure Functions デプロイ (func azure functionapp publish) ---"
cd "${SRC_DIR}"
func azure functionapp publish "${FUNC_APP_NAME}" \
  --python \
  --build remote \
  --output json > /tmp/deploy_output.json 2>&1 || {
    echo "❌ デプロイ失敗。ログを確認してください:"
    cat /tmp/deploy_output.json
    exit 1
}
echo "✅ デプロイ完了"

# ---- Step 3: エンドポイント URL 取得 ----
echo ""
echo "--- Step 3: エンドポイント URL 取得 ---"
FUNC_URL=$(az functionapp show \
  --name "${FUNC_APP_NAME}" \
  --resource-group "${RG_NAME}" \
  --query "defaultHostName" -o tsv)
BASE_URL="https://${FUNC_URL}/api"
echo "✅ ベース URL: ${BASE_URL}"

# ---- Step 4: endpoints.md 更新 ----
echo ""
echo "--- Step 4: docs/endpoints.md 更新 ---"
DEPLOY_DATE=$(date -u +"%Y-%m-%d %H:%M UTC")
cat > "${ENDPOINTS_FILE}" << ENDPOINTS
# After-Hours Agents — デプロイ済みエンドポイント

> 最終デプロイ: ${DEPLOY_DATE}
> 環境: ${ENV}
> Function App: \`${FUNC_APP_NAME}\`
> ベース URL: \`${BASE_URL}\`

## ヘルスチェック

\`\`\`
GET ${BASE_URL}/health
\`\`\`

## 昼レーン（Daytime Lane）

| メソッド | パス | 説明 |
|---------|------|------|
| POST | \`${BASE_URL}/day/analyze\` | 澪による手動分析（デバッグ用）|
| POST | \`${BASE_URL}/day/send-card\` | Teams Adaptive Card 送信 |
| POST | \`${BASE_URL}/day/approve\` | Copilot Studio 承認 Webhook |
| GET  | \`${BASE_URL}/day/incidents\` | インシデント一覧取得 |

## 夜レーン（Nighttime Lane）

| メソッド | パス | 説明 |
|---------|------|------|
| POST | \`${BASE_URL}/night/nocturne/start\` | 夜間 Group Chat 手動起動 |
| POST | \`${BASE_URL}/night/pr-draft\` | GitHub PR Draft 作成 |
| GET  | \`${BASE_URL}/night/summary\` | 最新振り返りサマリー取得 |
| POST | \`${BASE_URL}/morning/digest/test\` | Morning Digest 手動送信 |

## ハッカソン提出用 URL

Web アプリ URL（必須提出物）:
\`\`\`
${BASE_URL}/health
\`\`\`
ENDPOINTS

echo "✅ docs/endpoints.md を更新しました"
echo ""
echo "=== デプロイ完了 ==="
echo "  ハッカソン提出 URL: ${BASE_URL}/health"
