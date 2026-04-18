from __future__ import annotations

import os
from typing import Any

from azure.cosmos import CosmosClient, PartitionKey, exceptions
from azure.cosmos.aio import CosmosClient as AsyncCosmosClient

_ENDPOINT = os.environ["COSMOS_ENDPOINT"]
_KEY = os.environ["COSMOS_KEY"]
_DATABASE = os.environ.get("COSMOS_DATABASE", "after-hours-agents")

CONTAINER_SHARED_CORE = "shared_core"
CONTAINER_PRIVATE_EPISODIC = "private_episodic"


def _get_sync_client() -> CosmosClient:
    return CosmosClient(_ENDPOINT, credential=_KEY)


def _get_async_client() -> AsyncCosmosClient:
    return AsyncCosmosClient(_ENDPOINT, credential=_KEY)


class SharedCoreRepository:
    """shared_core コンテナの読み書きを担当する同期リポジトリ。"""

    def __init__(self) -> None:
        client = _get_sync_client()
        db = client.get_database_client(_DATABASE)
        self._container = db.get_container_client(CONTAINER_SHARED_CORE)

    def upsert(self, item: dict[str, Any]) -> dict[str, Any]:
        return self._container.upsert_item(item)

    def get(self, item_id: str, partition_key: str) -> dict[str, Any]:
        return self._container.read_item(item_id, partition_key=partition_key)

    def query(self, query: str, parameters: list[dict] | None = None) -> list[dict[str, Any]]:
        params = parameters or []
        return list(self._container.query_items(query=query, parameters=params, enable_cross_partition_query=True))

    def delete(self, item_id: str, partition_key: str) -> None:
        self._container.delete_item(item_id, partition_key=partition_key)


class PrivateEpisodicRepository:
    """private_episodic コンテナの読み書きを担当する同期リポジトリ。
    パーティションキーは agent_id。自分の agent_id 以外は read 禁止。
    """

    def __init__(self, agent_id: str) -> None:
        self._agent_id = agent_id
        client = _get_sync_client()
        db = client.get_database_client(_DATABASE)
        self._container = db.get_container_client(CONTAINER_PRIVATE_EPISODIC)

    def upsert(self, item: dict[str, Any]) -> dict[str, Any]:
        if item.get("agent_id") != self._agent_id:
            raise PermissionError(f"agent_id mismatch: {item.get('agent_id')} != {self._agent_id}")
        return self._container.upsert_item(item)

    def get(self, item_id: str) -> dict[str, Any]:
        return self._container.read_item(item_id, partition_key=self._agent_id)

    def query(self, query: str, parameters: list[dict] | None = None) -> list[dict[str, Any]]:
        params = parameters or []
        return list(self._container.query_items(query=query, parameters=params, partition_key=self._agent_id))

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
