"""Explicit storage selection. Cloud mode never falls back to local SQLite."""

import os
from pathlib import Path
from urllib.parse import urlparse

from counterpress.history import HistoryStore, SQLiteHistoryStore


def configured_store(db_path: str | Path) -> HistoryStore:
    mode = os.environ.get("COUNTERPRESS_STORAGE", "sqlite")
    if mode == "sqlite":
        return SQLiteHistoryStore(db_path)
    if mode != "cosmos":
        raise ValueError("COUNTERPRESS_STORAGE must be sqlite or cosmos")
    from azure.cosmos import CosmosClient
    from azure.identity import AzureCliCredential, ManagedIdentityCredential
    from counterpress.cosmos_history import CosmosHistoryStore

    endpoint = os.environ.get("COUNTERPRESS_COSMOS_ENDPOINT", "")
    parsed = urlparse(endpoint)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.path not in ("", "/")):
        raise ValueError("A valid HTTPS Cosmos endpoint is required")
    database = os.environ.get("COUNTERPRESS_COSMOS_DATABASE", "counterpress")
    container = os.environ.get("COUNTERPRESS_COSMOS_CONTAINER", "histories")
    auth = os.environ.get("COUNTERPRESS_COSMOS_AUTH", "managed-identity")
    if auth == "managed-identity":
        credential = ManagedIdentityCredential(client_id=os.environ.get("COUNTERPRESS_COSMOS_CLIENT_ID"))
    elif auth == "azure-cli":
        credential = AzureCliCredential(process_timeout=10)
    else:
        raise ValueError("Cosmos authentication must be managed-identity or azure-cli")
    client = CosmosClient(endpoint, credential=credential, consistency_level="Session",
                         connection_timeout=5, read_timeout=10, retry_total=2,
                         retry_write=0, retry_backoff_max=5, logging_enable=False)
    # Infrastructure owns database/container creation and RBAC, never the app.
    return CosmosHistoryStore(client.get_database_client(database).get_container_client(container))
