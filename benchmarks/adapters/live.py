"""Deliberate local-model opt-in; never pulls models or opens a cloud endpoint."""
from __future__ import annotations

import json
from urllib.request import ProxyHandler, build_opener

from oomp.providers.ollama import OllamaEmbeddingProvider, _NoRedirect


def inventory():
    opener=build_opener(ProxyHandler({}),_NoRedirect())
    try:
        with opener.open("http://127.0.0.1:11434/api/tags",timeout=5) as response:
            raw=response.read(1_000_001)
        if len(raw)>1_000_000:raise ValueError("inventory too large")
        document=json.loads(raw)
        return {m["name"]:{"name":m["name"],"digest":m.get("digest"),"size_bytes":m.get("size")}
                for m in document["models"]}
    except Exception:
        return {}


def embedding_provider(config,enabled):
    if not enabled:return None,{"status":"not_enabled"}
    models=inventory()
    if config.embedding_model not in models:return None,{"status":"unavailable","reason":"installed_model_not_found_or_service_unhealthy"}
    provider=OllamaEmbeddingProvider(model=config.embedding_model,dimension=config.embedding_dimension,
        version=config.embedding_version,timeout_seconds=60)
    try:provider.embed(("Synthetic benchmark health check.",))
    except Exception:return None,{"status":"unavailable","reason":"embedding_health_check_failed",**models[config.embedding_model]}
    return provider,{"status":"ready",**models[config.embedding_model],"space":provider.space.model_dump(mode="json"),
                    "endpoint_policy":"literal_loopback_no_proxy_no_redirect","truncate":False}
