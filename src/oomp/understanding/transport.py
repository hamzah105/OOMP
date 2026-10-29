"""Literal-loopback HTTP, no proxies/redirects, bounded bytes and wall time."""
from __future__ import annotations

import http.client
import ipaddress
import json
import socket
import threading
import time
from urllib.parse import urlsplit


class ExtractionUnavailable(ValueError):
    def __init__(self, code="extraction_provider_unavailable"):
        self.code = code
        super().__init__(code)


def loopback_endpoint(endpoint):
    try:
        parsed = urlsplit(endpoint)
        address = ipaddress.ip_address(parsed.hostname or "")
        if (parsed.scheme != "http" or not address.is_loopback or parsed.username is not None
                or parsed.password is not None or parsed.path not in {"", "/"}
                or parsed.query or parsed.fragment or parsed.port is None or not 1 <= parsed.port <= 65535):
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError("extraction_endpoint_requires_literal_loopback_http") from None
    return parsed.hostname, parsed.port


def request_json(endpoint, path, *, payload=None, timeout=3, max_bytes=65536):
    host, port = loopback_endpoint(endpoint)
    started = time.monotonic()
    connection = http.client.HTTPConnection(host, port, timeout=timeout)
    watchdog = None
    try:
        connection.connect()
        owned_socket = connection.sock
        def expire():
            try:
                owned_socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        remaining = timeout - (time.monotonic() - started)
        if remaining <= 0:
            raise ExtractionUnavailable("extraction_provider_timeout")
        watchdog = threading.Timer(remaining, expire)
        watchdog.daemon = True
        watchdog.start()
        body = json.dumps(payload, ensure_ascii=True, allow_nan=False).encode() if payload is not None else None
        if body is not None and len(body) > 65536:
            raise ExtractionUnavailable("extraction_request_limit")
        connection.request("POST" if payload is not None else "GET", path, body=body,
                           headers={"Content-Type": "application/json", "Accept": "application/json", "Connection": "close"})
        response = connection.getresponse()
        if response.status != 200:
            raise ExtractionUnavailable("extraction_provider_status")
        chunks, size = [], 0
        while True:
            if time.monotonic() - started >= timeout:
                raise ExtractionUnavailable("extraction_provider_timeout")
            chunk = response.read1(min(4096, max_bytes + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
            if size > max_bytes:
                raise ExtractionUnavailable("extraction_response_limit")
        result = json.loads(b"".join(chunks))
        if not isinstance(result, dict):
            raise ExtractionUnavailable("extraction_response_invalid")
        return result
    except ExtractionUnavailable:
        raise
    except (OSError, TimeoutError, ValueError, UnicodeError, RecursionError, http.client.HTTPException):
        code = "extraction_provider_timeout" if time.monotonic() - started >= timeout else "extraction_provider_unavailable"
        raise ExtractionUnavailable(code) from None
    finally:
        if watchdog is not None:
            watchdog.cancel()
        connection.close()
