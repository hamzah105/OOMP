"""Explicit MCP CLI. Diagnostics never print configuration values or secrets."""
from __future__ import annotations

import importlib.metadata
import json
import sys
from pathlib import Path

from .configuration import ServerConfiguration, Grant, load_configuration


def configure_parser(subparsers):
    parser = subparsers.add_parser("mcp", help="serve or configure the optional local MCP interface")
    commands = parser.add_subparsers(dest="mcp_command")
    for operation in ("serve", "check"):
        item = commands.add_parser(operation, help="run the MCP server" if operation == "serve" else "check MCP readiness without creating a database")
        item.add_argument("--config", metavar="PATH", help="explicit server configuration (or OOMP_MCP_CONFIG)")
        item.add_argument("--transport", choices=("stdio", "streamable-http"))
    config = commands.add_parser("config", help="print placeholder configuration JSON; does not edit host files")
    config.add_argument("--format", choices=("client", "server"), default="client")
    config.add_argument("--transport", choices=("stdio", "streamable-http"), default="stdio")
    config.add_argument("--config", required=True, metavar="PATH")
    config.add_argument("--db", metavar="PATH")
    config.add_argument("--tenant")
    config.add_argument("--namespace")
    config.add_argument("--principal")
    config.add_argument("--host", choices=("127.0.0.1", "::1"), default="127.0.0.1")
    config.add_argument("--port", type=int, default=8765)
    return parser


def _sdk_ready():
    try:
        version = importlib.metadata.version("mcp")
        parts = tuple(int(p) for p in version.split("."))
        if not (len(parts) == 3 and (2, 3, 0) <= parts < (2, 4, 0)):
            raise ValueError("unsupported SDK")
        return version
    except (importlib.metadata.PackageNotFoundError, ValueError):
        raise RuntimeError('Install the optional integration: python -m pip install -e ".[mcp]"') from None


def _generate(args):
    path = str(Path(args.config).expanduser().resolve())
    if args.format == "server":
        if not all((args.db, args.tenant, args.namespace, args.principal)):
            raise ValueError("server generation requires explicit database and scope")
        grant = Grant(grant_id="host-read", principal_id=args.principal,
                      tenant_id=args.tenant, namespace=args.namespace,
                      bearer_token_env="OOMP_MCP_TOKEN" if args.transport == "streamable-http" else None)
        config = ServerConfiguration(
            database=str(Path(args.db).expanduser().resolve()), transport=args.transport,
            stdio_grant=grant if args.transport == "stdio" else None,
            http_grants=(grant,) if args.transport == "streamable-http" else (),
            host=args.host, port=args.port,
        )
        return config.model_dump(mode="json", exclude_none=True)
    if args.transport == "stdio":
        return {"mcpServers": {"oomp": {
            "command": str(Path(sys.executable).resolve()),
            "args": ["-m", "oomp", "mcp", "serve", "--config", path, "--transport", "stdio"],
        }}}
    config = load_configuration(path, "streamable-http")
    return {"mcpServers": {"oomp": {
        "url": config.endpoint, "headers": {"Authorization": "Bearer <HOST_SUPPLIED_SECRET>"},
    }}}


def mcp_command(args):
    try:
        if args.mcp_command == "config":
            print(json.dumps(_generate(args), indent=2, ensure_ascii=True))
            return 0
        sdk_version = _sdk_ready()
        config = load_configuration(args.config, args.transport)
        if args.mcp_command == "check":
            from .server import build_server
            server = build_server(config)
            grants = ((config.stdio_grant,) if config.transport == "stdio" else config.http_grants)
            for grant in grants:
                if not server.resolver._live(grant):
                    raise ValueError("expired grant")
            print(json.dumps({
                "ready": True, "sdk": sdk_version, "transport": config.transport,
                "profile": config.profile, "schema_version": 5,
                "mind_worker_started": False,
            }, separators=(",", ":")))
            return 0
        from .server import serve
        serve(config)
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as error:
        from .errors import classify
        if isinstance(error, RuntimeError) and str(error).startswith("Install the optional integration:"):
            print(str(error), file=sys.stderr)
        else:
            print("MCP operation failed (" + classify(error) + "). Check explicit configuration, credentials and schema v5 readiness.",
                  file=sys.stderr)
        return 1