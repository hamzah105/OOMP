"""Trusted local acquisition administration; no new MCP authority."""
from __future__ import annotations

import json


def configure(subparsers):
    parser = subparsers.add_parser("understand", help="inspect episodes or preview bounded consented reprocessing")
    commands = parser.add_subparsers(dest="understand_command", required=True)
    for name in ("reprocess", "episodes", "inspect"):
        command = commands.add_parser(name)
        command.add_argument("--db", required=True)
        command.add_argument("--tenant", required=True)
        command.add_argument("--namespace", required=True)
        command.add_argument("--principal", required=True)
        if name == "reprocess":
            command.add_argument("--event-id", action="append", required=True)
            command.add_argument("--extraction-mode", choices=("rules", "local-llm"), default="rules")
            command.add_argument("--extraction-model")
            command.add_argument("--extraction-endpoint", default="http://127.0.0.1:11434")
            command.add_argument("--apply", action="store_true")
            command.add_argument("--consented", action="store_true")
            command.add_argument("--plan-digest")
        else:
            command.add_argument("--show-content", action="store_true")
            if name == "inspect":
                command.add_argument("--episode-id", required=True)
            else:
                command.add_argument("--limit", type=int, default=20)


def command(args):
    from oomp.domain.models import AuthorizedScope
    from oomp.product.safety import safe_path
    from .contracts import ExtractionConfiguration
    from .admin import reprocess, episodes
    try:
        scope = AuthorizedScope(tenant_id=args.tenant, namespace=args.namespace, principal_id=args.principal)
        path = safe_path(args.db)
        if args.understand_command == "reprocess":
            config = ExtractionConfiguration(mode=args.extraction_mode, model=args.extraction_model, endpoint=args.extraction_endpoint)
            result = reprocess(path, scope, args.event_id, config, apply=args.apply,
                consented=args.consented, plan_digest=args.plan_digest)
        else:
            result = episodes(path, scope, limit=getattr(args, "limit", 20),
                episode_id=getattr(args, "episode_id", None), show_content=args.show_content)
        print(json.dumps(result))
        return 0
    except Exception:
        print(json.dumps({"ok": False, "code": "understanding_operation_refused"}))
        return 1
