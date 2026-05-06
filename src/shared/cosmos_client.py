from __future__ import annotations

import logging
import os
from typing import Any

from azure.cosmos import CosmosClient, PartitionKey, exceptions
from azure.cosmos.aio import CosmosClient as AsyncCosmosClient
from azure.identity import DefaultAzureCredential, ManagedIdentityCredential

logger = logging.getLogger(__name__)

_ENDPOINT = os.environ["COSMOS_ENDPOINT"]
_DATABASE = os.environ.get("COSMOS_DATABASE", "after-hours-agents")

CONTAINER_SHARED_CORE = "shared_core"
CONTAINER_PRIVATE_EPISODIC = "private_episodic"


def _get_credential(agent_id_env: str = "") -> Any:
    """Entra Agent ID / Managed Identity / COSMOS_KEY の優先順で認証情報を返す。

    優先順:
    1. agent_id_env が指定されていて環境変数に値がある → ManagedIdentityCredential
    2. COSMOS_KEY 環境変数がある → マスターキー（ローカル開発専用）
    3. 上記いずれもない → DefaultAzureCredential（az login 等）
    """
    if agent_id_env:
        client_id = os.environ.get(agent_id_env)
        if client_id:
            logger.debug("Using ManagedIdentityCredential for %s", agent_id_env)
            return ManagedIdentityCredential(client_id=client_id)

    cosmos_key = os.environ.get("COSMOS_KEY")
    if cosmos_key:
        logger.debug("Using COSMOS_KEY (local dev fallback)")
        return cosmos_key

    logger.debug("Using DefaultAzureCredential")
    return DefaultAzureCredential()


def _get_sync_client(agent_id_env: str = "") -> CosmosClient:
    return CosmosClient(_ENDPOINT, credential=_get_credential(agent_id_env))


def _get_async_client(agent_id_env: str = "") -> AsyncCosmosClient:
    return AsyncCosmosClient(_ENDPOINT, credential=_get_credential(agent_id_env))


class SharedCoreRepository:
    """shared_core コンテナの読み書きを担当する同期リポジトリ。"""

    def __init__(self, agent_id_env: str = "") -> None:
        client = _get_sync_client(agent_id_env)
        db = client.get_database_client(_DATABASE)
        self._container = db.get_container_client(CONTAINER_SHARED_CORE)

    def upsert(self, item: dict[str, Any]) -> dict[str, Any]:
        return self._container.upsert_item(item)

    def get(self, item_id: str, partition_key: str) -> dict[str, Any]:
        return self._container.read_item(item_id, partition_key=partition_key)

    def query(
        self,
        query: str,
        parameters: list[dict] | None = None,
        partition_key: str | None = None,
    ) -> list[dict[str, Any]]:
        params = parameters or []
        kwargs: dict[str, Any] = {}
        if partition_key is not None:
            kwargs["partition_key"] = partition_key
        else:
            kwargs["enable_cross_partition_query"] = True
        return list(self._container.query_items(query=query, parameters=params, **kwargs))

    def delete(self, item_id: str, partition_key: str) -> None:
        self._container.delete_item(item_id, partition_key=partition_key)


class PrivateEpisodicRepository:
    """private_episodic コンテナの読み書きを担当する同期リポジトリ。
    パーティションキーは agent_id。自分の agent_id 以外は read 禁止。
    """

    def __init__(self, agent_id: str, agent_id_env: str = "") -> None:
        self._agent_id = agent_id
        client = _get_sync_client(agent_id_env)
        db = client.get_database_client(_DATABASE)
        self._container = db.get_container_client(CONTAINER_PRIVATE_EPISODIC)

    def upsert(self, item: dict[str, Any]) -> dict[str, Any]:
        if item.get("agent_id") != self._agent_id:
            raise PermissionError(
                f"agent_id mismatch: {item.get('agent_id')} != {self._agent_id}"
            )
        return self._container.upsert_item(item)

    def get(self, item_id: str) -> dict[str, Any]:
        return self._container.read_item(item_id, partition_key=self._agent_id)

    def query(
        self, query: str, parameters: list[dict] | None = None
    ) -> list[dict[str, Any]]:
        params = parameters or []
        return list(
            self._container.query_items(
                query=query, parameters=params, partition_key=self._agent_id
            )
        )

    def delete(self, item_id: str) -> None:
        self._container.delete_item(item_id, partition_key=self._agent_id)


def ensure_containers_exist() -> None:
    """データベースとコンテナが存在しない場合に作成する（ローカル開発・初期セットアップ用）。"""
    client = _get_sync_client()
    db = client.create_database_if_not_exists(_DATABASE)
    db.create_container_if_not_exists(
        id=CONTAINER_SHARED_CORE,
        partition_key=PartitionKey(path="/container_type"),
    )
    db.create_container_if_not_exists(
        id=CONTAINER_PRIVATE_EPISODIC,
        partition_key=PartitionKey(path="/agent_id"),
    )
