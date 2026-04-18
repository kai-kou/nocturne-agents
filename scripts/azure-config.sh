#!/usr/bin/env bash
# scripts/azure-config.sh — Azure 非機密設定（リポジトリにコミット可能）
#
# このファイルは機密情報を含まない。AZURE_CLIENT_SECRET は含めない。
# 機密情報は .azure_creds に記載する（gitignore 対象）。

export AZURE_TENANT_ID="7cf9d310-b118-4a03-8758-4115537b368f"
export AZURE_SUBSCRIPTION_ID="8683076d-82bf-44be-8e42-6374b99f879d"
export AZURE_CLIENT_ID="7efbacf4-b815-4851-b565-06d7044bcfcd"
export AZURE_SP_APP_NAME="after-hours-agents-hackathon"
