"""Optional Rich/Questionary presentation with a dependency-free accessible path."""
from __future__ import annotations

import json
import os
import sys


class UI:
    def __init__(self, *, plain=False):
        self.plain = plain or "NO_COLOR" in os.environ or not sys.stdout.isatty()
        self.console = None
        if not self.plain:
            try:
                from rich.console import Console
                self.console = Console(highlight=False, markup=False)
            except ImportError:
                self.plain = True

    def welcome(self):
        if self.console:
            from rich.panel import Panel
            from rich.text import Text
            self.console.print(Panel(Text("OOMP\nMemory beyond the context window.\nPersistent history. Selective recall. Finite prompt."), border_style="cyan"))
        else:
            print("OOMP — Memory beyond the context window.")

    def line(self, outcome, message):
        if self.console:
            from rich.text import Text
            text = Text(outcome+"  "+message)
            text.stylize({"PASS": "green", "WARN": "yellow", "FAIL": "red", "NOT TESTED": "dim"}.get(outcome, "cyan"), 0, len(outcome))
            self.console.print(text)
        else:
            print(outcome+"  "+message)

    def choose(self, label, choices, default=None):
        if not self.plain and sys.stdin.isatty():
            try:
                import questionary
                return questionary.select(label, choices=list(choices), default=default or choices[0]).unsafe_ask()
            except ImportError:
                self.line("WARN", 'Optional keyboard menus unavailable. Install ".[ui]"; using numbered prompts.')
        for index, choice in enumerate(choices, 1):
            print(f"  {index}. {choice}")
        answer = input(label+f" [{default or choices[0]}]: ").strip()
        if not answer:
            return default or choices[0]
        if answer.isdecimal() and 1 <= int(answer) <= len(choices):
            return choices[int(answer)-1]
        if answer in choices:
            return answer
        raise ValueError("invalid selection")

    def text(self, label, default=""):
        if not self.plain and sys.stdin.isatty():
            try:
                import questionary
                return questionary.text(label, default=str(default)).unsafe_ask()
            except ImportError:
                pass
        return input(label+(f" [{default}]" if default else "")+": ").strip() or str(default)

    def confirm(self, label):
        return self.choose(label, ("No", "Yes"), "No") == "Yes"

    def preview(self, value):
        # JSON escapes control characters and prints credential references only.
        rendered = json.dumps(value, indent=2, ensure_ascii=True)
        if self.console:
            from rich.panel import Panel
            from rich.text import Text
            self.console.print(Panel(Text(rendered), title="Proposed changes", border_style="cyan"))
        else:
            print(rendered)

    def diagnostics(self, report):
        self.welcome()
        for check in report["checks"]:
            self.line(check["outcome"], check["id"]+": "+check["code"])
            if check["outcome"] in {"WARN", "FAIL", "NOT TESTED"} and check["recommendation"]:
                self.line("", "  "+check["recommendation"])

    def runtime(self, report):
        self.welcome()
        self.line("PASS" if report["state"] == "running" else "WARN", "Profile "+report["profile"]+": "+report["state"])
        for role, service in report.get("services", {}).items():
            outcome = "WARN" if service["ready"] and service.get("last_error_code") else "PASS" if service["ready"] else "FAIL"
            self.line(outcome, role+": "+("ready" if service["ready"] else "not ready"))
        if report.get("stdio"):
            self.line("NOT TESTED", report["stdio"])
