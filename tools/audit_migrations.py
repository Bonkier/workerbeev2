# SPDX-License-Identifier: GPL-3.0-or-later
"""Scan src/wbcore for legacy Locate* / win_* call sites and print a
migration plan. Read-only.

    python tools/audit_migrations.py            # text report
    python tools/audit_migrations.py --csv      # CSV
    python tools/audit_migrations.py --file PATH
"""
from __future__ import annotations

import argparse
import ast
import csv
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional


# Legacy patterns

_LEGACY_LOCATE_CLASSES = {"LocateRGB", "LocateGray", "LocateEdges"}
_LEGACY_LOCATE_METHODS = {"check", "locate", "try_locate", "locate_all"}
_LEGACY_WIN_FUNCTIONS = {
    "win_click",
    "win_moveTo",
    "win_dragTo",
    "win_get_position",
}
# `<preset>.button(...)` is the dominant legacy idiom; map each preset alias
# to a specific CallSite preset + method.
_LEGACY_PRESET_ALIASES = {
    "loc":        ("cs.loc",        "wait"),
    "click":      ("cs.click",      "click"),
    "now":        ("cs.now",        "find"),
    "try_click":  ("cs.try_click",  "click"),
    "now_click":  ("cs.now_click",  "click"),
    "loc_rgb":    ("cs_rgb.loc",    "wait"),
    "click_rgb":  ("cs_rgb.click",  "click"),
    "now_rgb":    ("cs_rgb.now",    "find"),
    "try_rgb":    ("cs_rgb.try_click", "click"),
    "try_loc":    ("cs.loc(error=True)", "wait"),
}


@dataclass(frozen=True)
class Finding:
    file: Path
    line: int
    col: int
    kind: str           # "Locate*.method" or "win_*"
    legacy_call: str
    suggested_call: str


def _color_mode_for_class(name: str) -> str:
    return {
        "LocateRGB": "ColorMode.RGB",
        "LocateGray": "ColorMode.GRAY",
        "LocateEdges": "ColorMode.EDGES",
    }.get(name, "ColorMode.RGB")


def _suggest_locate_call(class_name: str, method: str) -> str:
    """Legacy Locate*.method() -> new-API suggestion."""
    if method == "check":
        return (
            "verifier.click_when_found(...)  # if click=True; "
            "else verifier.wait_for(...)"
        )
    if method == "locate":
        return "finder.find(...)"
    if method == "try_locate":
        return "hit = finder.find(...); raise if hit is None"
    if method == "locate_all":
        return "finder.find_all(..., nms_threshold=threshold)"
    return "?"


def _suggest_win_call(name: str) -> str:
    return {
        "win_click": "mouse.click(point, **kwargs)",
        "win_moveTo": "mouse.move_to(point, **kwargs)",
        "win_dragTo": "mouse.drag_to(point, **kwargs)",
        "win_get_position": "mouse.position()",
    }.get(name, "?")


def _suggest_button_call(preset_name: str) -> str:
    """<preset>.button(...) -> new CallSite spelling."""
    target = _LEGACY_PRESET_ALIASES.get(preset_name)
    if target is None:
        return "?"
    cs_attr, method = target
    return f"{cs_attr}.{method}(name)  # ver= becomes .button(ver=...)"


class _Visitor(ast.NodeVisitor):
    def __init__(self, path: Path, source_lines: list[str]):
        self.path = path
        self.source_lines = source_lines
        self.findings: list[Finding] = []

    def visit_Call(self, node: ast.Call) -> None:
        # Attribute call: LocateRGB.check(...) or <preset>.button(...)
        if isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name):
                obj = node.func.value.id
                method = node.func.attr
                if obj in _LEGACY_LOCATE_CLASSES and method in _LEGACY_LOCATE_METHODS:
                    self._record(
                        node,
                        kind=f"{obj}.{method}",
                        suggested=_suggest_locate_call(obj, method),
                    )
                elif method == "button" and obj in _LEGACY_PRESET_ALIASES:
                    self._record(
                        node,
                        kind=f"{obj}.button",
                        suggested=_suggest_button_call(obj),
                    )
        elif isinstance(node.func, ast.Name):

            name = node.func.id
            if name in _LEGACY_WIN_FUNCTIONS:
                self._record(
                    node,
                    kind=name,
                    suggested=_suggest_win_call(name),
                )

        self.generic_visit(node)

    def _record(self, node: ast.Call, *, kind: str, suggested: str) -> None:
        # end_lineno (Py 3.8+) gives the whole multi-line call.
        start = node.lineno
        end = getattr(node, "end_lineno", start) or start
        snippet_lines = self.source_lines[start - 1: end]
        snippet = " ".join(line.strip() for line in snippet_lines)
        # Truncate so the report stays grep-friendly.
        if len(snippet) > 200:
            snippet = snippet[:197] + "..."
        self.findings.append(
            Finding(
                file=self.path,
                line=start,
                col=node.col_offset + 1,
                kind=kind,
                legacy_call=snippet,
                suggested_call=suggested,
            )
        )


def _scan_file(path: Path) -> list[Finding]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as ex:
        print(f"[skip] {path}: {ex}", file=sys.stderr)
        return []
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError as ex:
        print(f"[skip] {path}: syntax error at line {ex.lineno}", file=sys.stderr)
        return []
    v = _Visitor(path, text.splitlines())
    v.visit(tree)
    return v.findings


def _iter_python_files(root: Path) -> Iterable[Path]:
    for p in root.rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        # New pipeline modules contain no legacy calls by definition.
        if any(part in p.parts for part in (
            "detection", "regionspec", "vision", "input", "verifier"
        )):
            continue
        yield p


def _print_text(findings: list[Finding]) -> None:
    if not findings:
        print("No legacy call sites found.")
        return

    by_file: dict[Path, list[Finding]] = {}
    for f in findings:
        by_file.setdefault(f.file, []).append(f)

    print(f"{len(findings)} legacy call sites across {len(by_file)} files\n")
    for file in sorted(by_file):
        rows = by_file[file]
        print(f"=== {file} ({len(rows)} calls) ===")
        for r in rows:
            print(f"  L{r.line:4d}  [{r.kind}]")
            print(f"        legacy:    {r.legacy_call}")
            print(f"        suggested: {r.suggested_call}")
        print()


def _print_csv(findings: list[Finding]) -> None:
    writer = csv.writer(sys.stdout, lineterminator="\n")
    writer.writerow(["file", "line", "col", "kind", "legacy_call", "suggested_call"])
    for f in findings:
        writer.writerow([
            str(f.file), f.line, f.col, f.kind, f.legacy_call, f.suggested_call,
        ])


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--csv", action="store_true",
        help="emit CSV instead of human-readable text",
    )
    parser.add_argument(
        "--file", type=Path, default=None,
        help="audit just one file instead of the whole tree",
    )
    parser.add_argument(
        "--root", type=Path, default=None,
        help="root to scan (default: <repo>/src/wbcore)",
    )
    args = parser.parse_args(argv)

    if args.file is not None:
        files = [args.file]
    else:
        root = args.root or (Path(__file__).resolve().parents[1] / "src" / "wbcore")
        if not root.exists():
            print(f"error: scan root does not exist: {root}", file=sys.stderr)
            return 1
        files = list(_iter_python_files(root))

    findings: list[Finding] = []
    for path in files:
        findings.extend(_scan_file(path))

    findings.sort(key=lambda f: (str(f.file), f.line))

    if args.csv:
        _print_csv(findings)
    else:
        _print_text(findings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
