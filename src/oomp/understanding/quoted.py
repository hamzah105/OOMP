"""Bounded event-level quotation context, with conservative unmatched handling."""
from __future__ import annotations

import re


def quoted_context(content: str, start: int, end: int) -> bool:
    """Keep attribution when segmentation splits inside a quotation.

    No plaintext cache survives this bounded call. Unclosed quotes/code and
    reported speech conservatively retain attribution through the event.
    """
    intervals = []
    index, opened, closing = 0, None, None
    while index < len(content):
        if opened is not None:
            if content.startswith(closing, index):
                if closing == "'" and index > 0 and index + 1 < len(content) and content[index - 1].isalnum() and content[index + 1].isalnum():
                    index += 1
                    continue
                intervals.append((opened, index + len(closing)))
                index += len(closing)
                opened, closing = None, None
                continue
            index += 1
            continue
        tick = chr(96)
        fence = next((token for token in ("~~~", tick * 3, tick) if content.startswith(token, index)), None)
        if fence is not None:
            opened, closing = index, fence
            index += len(fence)
            continue
        character = content[index]
        if character in {'"', "\u201c", "\u2018", "'"}:
            single = character == "'"
            if not single or (index == 0 or not content[index - 1].isalnum()) and index + 1 < len(content) and not content[index + 1].isspace():
                opened, closing = index, {'"': '"', "\u201c": "\u201d", "\u2018": "\u2019", "'": "'"}[character]
        index += 1
    if opened is not None:
        intervals.append((opened, len(content)))
    if any(left < end and start < right for left, right in intervals):
        return True
    for match in re.finditer(r"(?m)^[ \t]*>", content):
        boundary = re.search(r"\n[ \t]*\n", content[match.start():])
        right = match.start() + boundary.start() if boundary else len(content)
        if match.start() < end and start < right:
            return True
    return re.search(r"\b(?:said|says|according to|quoted|claims that)\b", content[:start], re.I) is not None
