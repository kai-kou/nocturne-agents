from __future__ import annotations

import os

from azure.identity import DefaultAzureCredential, ManagedIdentityCredential


def get_agent_credential(agent_id_env: str) -> ManagedIdentityCredential | DefaultAzureCredential:
    """Entra Agent ID に対応する認証情報を返す。
    環境変数に Agent ID が設定されている場合は ManagedIdentityCredential を使用。
    ローカル開発時は DefaultAzureCredential にフォールバックする。
    """
    agent_client_id = os.environ.get(agent_id_env)
    if agent_client_id:
        return ManagedIdentityCredential(client_id=agent_client_id)
    return DefaultAzureCredential()


COSMOS_SCOPE = "https://cosmos.azure.com/.default"
TEAMS_SCOPE = "https://graph.microsoft.com/.default"
GITHUB_SCOPE = "api://github-pr-creator/.default"


def get_cosmos_token(agent_id_env: str) -> str:
    """Cosmos DB アクセス用トークンを取得する。"""
    credential = get_agent_credential(agent_id_env)
    token = credential.get_token(COSMOS_SCOPE)
    return token.token


def get_teams_token(agent_id_env: str) -> str:
    """Teams / Graph API アクセス用トークンを取得する。"""
    credential = get_agent_credential(agent_id_env)
    token = credential.get_token(TEAMS_SCOPE)
    return token.token
