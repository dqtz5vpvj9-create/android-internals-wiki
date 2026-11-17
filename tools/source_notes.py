#!/usr/bin/env python3
"""Move inline source audit records into Markdown footnotes."""
from __future__ import annotations

import argparse
import re
from pathlib import Path

ANNOTATION = re.compile(r"(?<!\\)\[((?:来源|已验证)\s*[:：][^\]\n]+)\](?!\()")
ANNOTATION_START = re.compile(r"(?<!\\)\[(?:来源|已验证)\s*[:：]")
INLINE_CODE = re.compile(r"(`+)(.*?)(\1)")
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
URL = re.compile(r"(?<!<)(?<!\]\()https?://[^\s；，、）)<>]+")


def source_notes(text: str) -> str:
    """Replace audit annotations outside code with ordinary footnotes."""
    original = text
    frontmatter = ""
    # Source files may contain YAML with their own provenance records.
    # Keep that metadata byte-for-byte and transform only the body.
    if text.startswith("---\n") or text.startswith("---\r\n"):
        boundary = re.search(r"^---[ \t]*\r?$", text[text.find("\n") + 1:], re.M)
        if boundary:
            offset = text.find("\n") + 1 + boundary.end()
            if text[offset:offset + 2] == "\r\n":
                offset += 2
            elif text[offset:offset + 1] == "\n":
                offset += 1
            frontmatter, text = text[:offset], text[offset:]
    labels: dict[str, str] = {}
    marker = "source-audit-note"
    while f"[^{marker}-" in text:
        marker += "x"
    fence_char = ""
    fence_len = 0
    out: list[str] = []

    def replace(value: str) -> str:
        if value not in labels:
            labels[value] = f"{marker}-{len(labels) + 1}"
        return f"[^{labels[value]}]"

    for line in text.splitlines(keepends=True):
        fence = FENCE.match(line)
        if fence:
            token = fence.group(1)
            if not fence_char:
                fence_char, fence_len = token[0], len(token)
            elif token[0] == fence_char and len(token) >= fence_len:
                fence_char, fence_len = "", 0
            out.append(line)
            continue
        if fence_char or line.startswith(("    ", "\t")) or re.match(r"^\[\^[^]]+\]:", line):
            out.append(line)
            continue
        # Records can contain code spans and Markdown links. Locate the
        # matching outer bracket without disturbing nested link labels.
        code_spans = [(code.start(), code.end()) for code in INLINE_CODE.finditer(line)]
        pieces = []
        cursor = search_at = 0
        while match := ANNOTATION_START.search(line, search_at):
            if any(start <= match.start() < end for start, end in code_spans):
                search_at = match.end()
                continue
            depth = 0
            end = match.start()
            while end < len(line):
                if line[end] == "\\":
                    end += 2
                    continue
                if line[end] == "[":
                    depth += 1
                elif line[end] == "]":
                    depth -= 1
                    if depth == 0:
                        break
                end += 1
            if depth:
                search_at = match.end()
                continue
            if end + 1 < len(line) and line[end + 1] == "(":
                start = end + 1
                parentheses = 0
                while end + 1 < len(line):
                    end += 1
                    if line[end] == "(":
                        parentheses += 1
                    elif line[end] == ")":
                        parentheses -= 1
                        if not parentheses:
                            break
                if parentheses:
                    search_at = start + 1
                    continue
                value = line[match.start():end + 1]
            else:
                value = line[match.start() + 1:end]
            pieces.append(line[cursor:match.start()])
            pieces.append(replace(value))
            cursor = search_at = end + 1
        pieces.append(line[cursor:])
        out.append("".join(pieces))

    if not labels:
        return original
    body = "".join(out).rstrip() + "\n\n"
    for value, label in labels.items():
        linked = URL.sub(lambda match: f"<{match.group(0)}>", value)
        body += f"[^{label}]: {linked}\n"
    return frontmatter + body


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    changed = 0
    for path in sorted(args.root.rglob("*.md")):
        original = path.read_text(encoding="utf-8")
        result = source_notes(original)
        if result != original:
            path.write_text(result, encoding="utf-8")
            changed += 1
    print(f"Moved source records to footnotes in {changed} files")


if __name__ == "__main__":
    main()
