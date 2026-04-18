#!/usr/bin/env bash
# scripts/provision.sh — After-Hours Agents Azure リソース自動プロビジョニング
#
# 自動化する範囲:
#   1. リソースグループ作成
#   2. Cosmos DB NoSQL (shared_core / private_episodic コンテナ)
#   3. Azure Functions (Python 3.11 / Consumption プラン)
#   4. User-Assigned Managed Identity x4 (mio-01 / toride-06 / yomi-04 / digest)
#   5. Cosmos DB RBAC ロール割り当て
#   4.5. 本家リポ (kai-kou/kinako-mocchi) GitHub Variables から X API 情報を自動取得
#   6. src/local.settings.json の自動生成
#
# X API 認証情報について:
#   - X Developer Portal のポリシー上、アプリ登録・Bearer Token 発行は API 自動化不可
#   - ただし本家リポ kai-kou/kinako-mocchi の GitHub Actions Variables に保存されていれば
#     GitHub API (GET /repos/{owner}/{repo}/actions/variables/{name}) で値を自動取得できる
#   - gh コマンドまたは GITHUB_TOKEN 環境変数があれば Step 4.5 で自動取得を試みる
#
# 使い方:
#   az login
#   bash scripts/provision.sh [dev|prod] [リソースグループ名] [リージョン]

set -euo pipefail

ENV="${1:-dev}"
RG="${2:-rg-after-hours-agents-${ENV}}"
LOCATION="${3:-japaneast}"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SUFFIX="aha-${ENV}"

echo "=== After-Hours Agents プロビジョニング開始 ==="
echo "  環境        : ${ENV}"
echo "  リソースグループ: ${RG}"
echo "  リージョン  : ${LOCATION}"

if ! az account show &>/dev/null; then
  echo "   az login されていません。自動認証を試みるにゃ..."
  if [ -f "${PROJECT_ROOT}/scripts/azure-auth.sh" ]; then
    bash "${PROJECT_ROOT}/scripts/azure-auth.sh"
  else
    echo "❌ scripts/azure-auth.sh が見つかりません。先に 'az login' を実行してください。"
    exit 1
  fi
fi

SUBSCRIPTION=$(az account show --query id -o tsv)
echo "✅ サブスクリプション: ${SUBSCRIPTION}"

# ---- Step 1: リソースグループ ----
echo ""
echo "--- Step 1: リソースグループ作成 ---"
az group create --name "${RG}" --location "${LOCATION}" --output none
echo "✅ ${RG} 作成完了"

# ---- Step 2: Bicep デプロイ（Cosmos DB + Functions + Identity + RBAC）----
echo ""
echo "--- Step 2: Bicep テンプレートデプロイ ---"
DEPLOY_OUT=$(az deployment group create \
  --resource-group "${RG}" \
  --template-file "${PROJECT_ROOT}/infra/main.bicep" \
  --parameters \
    location="${LOCATION}" \
    environment="${ENV}" \
    projectPrefix="aha" \
  --output json)

COSMOS_ENDPOINT=$(echo "${DEPLOY_OUT}" | python3 -c "import sys,json; print(json.load(sys.stdin)['properties']['outputs']['cosmosEndpoint']['value'])")
FUNCTION_APP_URL=$(echo "${DEPLOY_OUT}" | python3 -c "import sys,json; print(json.load(sys.stdin)['properties']['outputs']['functionAppUrl']['value'])")
echo "✅ Bicep デプロイ完了"
echo "   Cosmos DB エンドポイント: ${COSMOS_ENDPOINT}"
echo "   Functions URL           : ${FUNCTION_APP_URL}"

# ---- Step 3: Managed Identity の Client ID を取得 ----
echo ""
echo "--- Step 3: Managed Identity Client ID 取得 ---"
get_client_id() {
  az identity show \
    --resource-group "${RG}" \
    --name "agent-${1}" \
    --query clientId -o tsv
}
MIO_CLIENT_ID=$(get_client_id "mio-01")
TORIDE_CLIENT_ID=$(get_client_id "toride-06")
YOMI_CLIENT_ID=$(get_client_id "yomi-04")
DIGEST_CLIENT_ID=$(get_client_id "digest")
echo "✅ 全 Agent Identity Client ID 取得完了"

# ---- Step 4: Cosmos DB キー取得 ----
echo ""
echo "--- Step 4: Cosmos DB キー取得 ---"
COSMOS_ACCOUNT_NAME="cosmos-${SUFFIX}"
COSMOS_KEY=$(az cosmosdb keys list \
  --resource-group "${RG}" \
  --name "${COSMOS_ACCOUNT_NAME}" \
  --query primaryMasterKey -o tsv)
echo "✅ Cosmos DB キー取得完了"

# ---- Step 4.5: 本家リポ GitHub Variables から X API 情報を自動取得 ----
echo ""
echo "--- Step 4.5: X API 認証情報を本家リポ GitHub Variables から取得 ---"

# gh コマンドまたは GITHUB_TOKEN からトークンを取得
GH_TOKEN=""
if command -v gh &>/dev/null; then
  GH_TOKEN=$(gh auth token 2>/dev/null || echo "")
fi
if [ -z "${GH_TOKEN}" ] && [ -n "${GITHUB_TOKEN:-}" ]; then
  GH_TOKEN="${GITHUB_TOKEN}"
fi

SOURCE_REPO="kai-kou/kinako-mocchi"
X_API_BEARER_TOKEN="__SET_FROM_KINAKO_MOCCHI_ENV__"
X_API_KEY="__SET_FROM_KINAKO_MOCCHI_ENV__"
X_API_SECRET="__SET_FROM_KINAKO_MOCCHI_ENV__"
X_ACCESS_TOKEN="__SET_FROM_KINAKO_MOCCHI_ENV__"
X_ACCESS_TOKEN_SECRET="__SET_FROM_KINAKO_MOCCHI_ENV__"

fetch_github_var() {
  local var_name="$1"
  local result
  result=$(curl -s \
    -H "Authorization: Bearer ${GH_TOKEN}" \
    -H "Accept: application/vnd.github+json" \
    "https://api.github.com/repos/${SOURCE_REPO}/actions/variables/${var_name}" \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('value','__NOT_FOUND__'))" 2>/dev/null || echo "__NOT_FOUND__")
  echo "${result}"
}

if [ -n "${GH_TOKEN}" ]; then
  echo "   GitHub トークンを検出。本家リポ変数の取得を試みます..."
  # 変数名の候補（本家リポでの実際の命名に対応）
  for bearer_var in X_API_BEARER_TOKEN TWITTER_BEARER_TOKEN X_BEARER_TOKEN; do
    val=$(fetch_github_var "${bearer_var}")
    if [ "${val}" != "__NOT_FOUND__" ] && [ -n "${val}" ]; then
      X_API_BEARER_TOKEN="${val}"; echo "   ✅ Bearer Token 取得完了 (変数名: ${bearer_var})"; break
    fi
  done
  for key_var in X_API_KEY TWITTER_API_KEY X_CONSUMER_KEY; do
    val=$(fetch_github_var "${key_var}")
    if [ "${val}" != "__NOT_FOUND__" ] && [ -n "${val}" ]; then
      X_API_KEY="${val}"; echo "   ✅ API Key 取得完了 (変数名: ${key_var})"; break
    fi
  done
  for secret_var in X_API_SECRET TWITTER_API_SECRET X_CONSUMER_SECRET; do
    val=$(fetch_github_var "${secret_var}")
    if [ "${val}" != "__NOT_FOUND__" ] && [ -n "${val}" ]; then
      X_API_SECRET="${val}"; echo "   ✅ API Secret 取得完了 (変数名: ${secret_var})"; break
    fi
  done
  for at_var in X_ACCESS_TOKEN TWITTER_ACCESS_TOKEN; do
    val=$(fetch_github_var "${at_var}")
    if [ "${val}" != "__NOT_FOUND__" ] && [ -n "${val}" ]; then
      X_ACCESS_TOKEN="${val}"; echo "   ✅ Access Token 取得完了 (変数名: ${at_var})"; break
    fi
  done
  for ats_var in X_ACCESS_TOKEN_SECRET TWITTER_ACCESS_TOKEN_SECRET; do
    val=$(fetch_github_var "${ats_var}")
    if [ "${val}" != "__NOT_FOUND__" ] && [ -n "${val}" ]; then
      X_ACCESS_TOKEN_SECRET="${val}"; echo "   ✅ Access Token Secret 取得完了 (変数名: ${ats_var})"; break
    fi
  done

  # Variables に存在しない場合は Secrets を確認（値は取得不可だが存在確認は可能）
  if [ "${X_API_BEARER_TOKEN}" = "__SET_FROM_KINAKO_MOCCHI_ENV__" ]; then
    SECRETS_LIST=$(curl -s \
      -H "Authorization: Bearer ${GH_TOKEN}" \
      -H "Accept: application/vnd.github+json" \
      "https://api.github.com/repos/${SOURCE_REPO}/actions/secrets" \
      | python3 -c "import sys,json; d=json.load(sys.stdin); [print(s['name']) for s in d.get('secrets',[])]" 2>/dev/null || echo "")
    if echo "${SECRETS_LIST}" | grep -qiE "X_API|TWITTER|BEARER"; then
      echo "   ⚠️  X API 認証情報は本家リポの GitHub Secrets に存在します（Variables ではない）"
      echo "      Secrets の値は API で取得できません。以下のコマンドで手動で転記してください:"
      echo "      gh secret list --repo ${SOURCE_REPO}"
      echo "      → 該当する Secret 名を確認後、GitHub UI または gh で値を確認してください"
    else
      echo "   ⚠️  本家リポに X API Variables/Secrets が見つかりませんでした"
      echo "      src/local.settings.json の X_API_* を手動で設定してください"
    fi
  fi
else
  echo "   ⚠️  GitHub トークンが見つかりません。以下のいずれかで解決できます:"
  echo "      1. gh auth login を実行する"
  echo "      2. export GITHUB_TOKEN=<your-token> を設定してから再実行する"
  echo "      X API 情報は src/local.settings.json で手動設定が必要です"
fi

# ---- Step 5: src/local.settings.json 生成 ----
echo ""
echo "--- Step 5: src/local.settings.json 生成 ---"
LOCAL_SETTINGS="${PROJECT_ROOT}/src/local.settings.json"

if [ -f "${LOCAL_SETTINGS}" ]; then
  cp "${LOCAL_SETTINGS}" "${LOCAL_SETTINGS}.bak"
  echo "   既存ファイルを ${LOCAL_SETTINGS}.bak にバックアップ"
fi

cat > "${LOCAL_SETTINGS}" <<EOF
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "COSMOS_ENDPOINT": "${COSMOS_ENDPOINT}",
    "COSMOS_KEY": "${COSMOS_KEY}",
    "COSMOS_DATABASE": "after-hours-agents",
    "ENTRA_AGENT_ID_MIO_01": "${MIO_CLIENT_ID}",
    "ENTRA_AGENT_ID_TORIDE_06": "${TORIDE_CLIENT_ID}",
    "ENTRA_AGENT_ID_YOMI_04": "${YOMI_CLIENT_ID}",
    "ENTRA_AGENT_ID_DIGEST": "${DIGEST_CLIENT_ID}",
    "X_API_BEARER_TOKEN": "__SET_FROM_KINAKO_MOCCHI_ENV__",
    "X_API_KEY": "__SET_FROM_KINAKO_MOCCHI_ENV__",
    "X_API_SECRET": "__SET_FROM_KINAKO_MOCCHI_ENV__",
    "X_ACCESS_TOKEN": "__SET_FROM_KINAKO_MOCCHI_ENV__",
    "X_ACCESS_TOKEN_SECRET": "__SET_FROM_KINAKO_MOCCHI_ENV__",
    "TEAMS_WEBHOOK_URL": "__SET_MANUALLY__",
    "GITHUB_TOKEN": "__SET_MANUALLY__",
    "GITHUB_REPO": "kai-kou/kinako-mocchi-hackathon",
    "AZURE_OPENAI_ENDPOINT": "__SET_MANUALLY__",
    "AZURE_OPENAI_API_KEY": "__SET_MANUALLY__",
    "AZURE_OPENAI_DEPLOYMENT": "gpt-4o",
    "RISK_SCORE_THRESHOLD": "70"
  }
}
EOF
echo "✅ src/local.settings.json 生成完了"
echo ""
echo "=== プロビジョニング完了 ==="
echo ""

# 未設定の変数を確認して最終案内を表示
REMAINING=$(grep -c "__SET_" "${LOCAL_SETTINGS}" || true)
if [ "${REMAINING}" -eq 0 ]; then
  echo "🎉 全設定が自動入力されました！"
  echo "   次のコマンドでローカルテストを開始できます:"
  echo "   cd src && func start"
else
  echo "⚠️  src/local.settings.json に手動設定が ${REMAINING} 件残っています:"
  grep "__SET_" "${LOCAL_SETTINGS}" | awk -F'"' '{print "   -", $2}'
  echo ""
  echo "設定後に: cd src && func start"
fi
