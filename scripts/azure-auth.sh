#!/usr/bin/env bash
# scripts/azure-auth.sh — Azure 認証自動化スクリプト
#
# 認証優先順位:
#   1. 既に az login 済みなら何もしない
#   2. AZURE_CLIENT_SECRET が環境変数にあればサービスプリンシパルで自動ログイン
#   3. .azure_creds ファイルがあれば読み込んで SP 認証
#   4. フォールバック: デバイスコードフロー（ユーザーがスマホで承認）
#
# 使い方:
#   source scripts/azure-auth.sh   # 環境変数を継承したい場合
#   bash scripts/azure-auth.sh     # 単独実行（az CLI に認証状態を注入）

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# 非機密設定を読み込む
source "${PROJECT_ROOT}/scripts/azure-config.sh"

echo "=== Azure 認証 ==="
echo "  テナント ID   : ${AZURE_TENANT_ID}"
echo "  サブスクリプション: ${AZURE_SUBSCRIPTION_ID}"

# ---- Step 1: 既にログイン済みか確認 ----
if az account show &>/dev/null; then
  CURRENT_SUB=$(az account show --query id -o tsv)
  if [ "${CURRENT_SUB}" = "${AZURE_SUBSCRIPTION_ID}" ]; then
    echo "✅ 既に認証済みにゃ（サブスクリプション一致）"
    exit 0
  fi
  echo "   別のサブスクリプションでログイン中。切り替えるにゃ..."
  az account set --subscription "${AZURE_SUBSCRIPTION_ID}" && echo "✅ サブスクリプション切り替え完了" && exit 0
fi

# ---- Step 2: クレデンシャル復元（GitHub Variables から自動取得）----
# Claude Code クラウド環境ではセッション間でファイルが消えるため自動復元を試みる
if [ ! -f "${PROJECT_ROOT}/.azure_creds" ] || ! grep -q "AZURE_CLIENT_SECRET" "${PROJECT_ROOT}/.azure_creds" 2>/dev/null; then
  echo "   .azure_creds なし → GitHub Variables から自動復元を試みるにゃ..."
  bash "${PROJECT_ROOT}/scripts/restore-azure-creds.sh" 2>/dev/null || true
fi

if [ -f "${PROJECT_ROOT}/.azure_creds" ]; then
  echo "   .azure_creds を検出。SP 認証を試みるにゃ..."
  # shellcheck source=/dev/null
  source "${PROJECT_ROOT}/.azure_creds"
fi

# ---- Step 3: SP 認証（AZURE_CLIENT_SECRET があれば） ----
if [ -n "${AZURE_CLIENT_SECRET:-}" ]; then
  echo "   サービスプリンシパルで認証中..."
  az login \
    --service-principal \
    --tenant "${AZURE_TENANT_ID}" \
    --username "${AZURE_CLIENT_ID}" \
    --password "${AZURE_CLIENT_SECRET}" \
    --output none
  az account set --subscription "${AZURE_SUBSCRIPTION_ID}" --output none
  echo "✅ SP 認証成功にゃ！"
  exit 0
fi

# ---- Step 4: デバイスコードフロー（フォールバック） ----
echo ""
echo "⚠️  AZURE_CLIENT_SECRET が見つかりませんでした。"
echo "   デバイスコードフローで認証するにゃ。"
echo ""

# az login --use-device-code を使う（標準フロー・トークンキャッシュを正しく保存）
az login \
  --use-device-code \
  --tenant "${AZURE_TENANT_ID}" \
  --output none

az account set --subscription "${AZURE_SUBSCRIPTION_ID}" --output none
echo "✅ デバイスコード認証成功にゃ！"
echo ""
echo "次回セッション用に GitHub Secrets/Variables を設定するには:"
echo "  bash scripts/set-github-secrets.sh"
