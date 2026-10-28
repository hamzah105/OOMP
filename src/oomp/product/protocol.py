"""Bounded actual SDK probes, not TCP-only health claims or a new MCP protocol."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import logging

from .safety import ProductError


@asynccontextmanager
async def session(profile, environment, *, role="read", timeout=4):
    try:
        import httpx2
        from mcp import Client, StdioServerParameters
        from mcp.client.streamable_http import streamable_http_client
    except ImportError:
        raise ProductError("mcp_dependency_missing") from None
    previous = logging.root.manager.disable
    logging.disable(logging.CRITICAL)  # parser exceptions can contain remote input
    try:
        read, writers = profile.grants()
        grant = read if role == "read" else writers[role]
        class LimitedStream(httpx2.AsyncByteStream):
            def __init__(self, stream):
                self.stream = stream
            async def __aiter__(self):
                size = 0
                async for chunk in self.stream:
                    size += len(chunk)
                    if size > 300000:
                        raise ProductError("mcp_result_limit")
                    yield chunk
            async def aclose(self):
                await self.stream.aclose()
        class Transport(httpx2.AsyncHTTPTransport):
            async def handle_async_request(self, request):
                response = await super().handle_async_request(request)
                response.stream = LimitedStream(response.stream)
                return response
        if profile.transport != "streamable-http":
            raise ProductError("stdio_is_host_owned")
        async with httpx2.AsyncClient(headers={"Authorization": "Bearer " + environment[grant.bearer_token_env]},
                                     trust_env=False, timeout=timeout, transport=Transport()) as http:
            async with Client(streamable_http_client(profile.server().endpoint, http_client=http)) as client:
                yield client
    finally:
        logging.disable(previous)


def call(profile, environment, name="memory.status", arguments=None, *, role="read", timeout=4):
    async def operation():
        async with session(profile, environment, role=role, timeout=timeout) as client:
            result = await client.call_tool(name, arguments or {})
            if result.is_error:
                raise ProductError("mcp_authorization_or_tool_failed")
            if not isinstance(result.structured_content, dict):
                raise ProductError("invalid_mcp_response")
            return result.structured_content
    try:
        return asyncio.run(asyncio.wait_for(operation(), timeout + 1))
    except ProductError:
        raise
    except Exception:
        raise ProductError("mcp_handshake_or_authorization_failed") from None
