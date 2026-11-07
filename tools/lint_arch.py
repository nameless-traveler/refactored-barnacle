#!/usr/bin/env python3
"""Mechanical architecture and taste checks. Every error says how to fix it, so the message
lands in the agent's context as remediation instructions (the 'custom lint' idea from the article).
Agents cannot edit this file.
"""
from __future__ import annotations

import ast
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src", "regex_engine")
MAX_LINES = 400
AGENTS_MAX_LINES = 120

# The engine must be its own implementation, not a wrapper around the oracle.
BANNED_MODULES = {
    "re", "regex", "sre_compile", "sre_parse", "sre_constants", "_sre", "fnmatch",
    "importlib", "subprocess", "ctypes", "os", "sys", "builtins",
}
BANNED_CALLS = {"eval", "exec", "__import__"}

# Layers, lowest first. A module may only import modules BELOW it.
LAYERS = ["nodes", "parser", "matcher", "__init__"]

errors: list[str] = []


def err(path: str, line: int, msg: str, fix: str) -> None:
    errors.append("LINT %s:%d: %s\n  FIX: %s" % (os.path.relpath(path, ROOT), line, msg, fix))


def sibling_imports(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level >= 1 and node.module:
                names.add(node.module.split(".")[0])
            elif node.level >= 1:
                names.update(a.name for a in node.names)
            elif node.module and node.module.startswith("regex_engine."):
                names.add(node.module.split(".")[1])
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name.startswith("regex_engine."):
                    names.add(a.name.split(".")[1])
    return names


def check_source() -> None:
    if not os.path.isdir(SRC):
        err(SRC, 0, "src/regex_engine is missing", "restore the package directory")
        return
    for name in sorted(os.listdir(SRC)):
        if not name.endswith(".py"):
            continue
        path = os.path.join(SRC, name)
        text = open(path).read()
        if text.count("\n") + 1 > MAX_LINES:
            err(path, 1, "file is longer than %d lines" % MAX_LINES, "split it into smaller modules that respect the layer order")
        tree = ast.parse(text)
        module = name[:-3]
        for node in ast.walk(tree):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                mods = [node.module.split(".")[0]]
            for m in mods:
                if m in BANNED_MODULES:
                    err(path, node.lineno, "import of '%s' is not allowed in the engine" % m,
                        "implement the behaviour yourself with plain Python; the engine may not use re, os, sys, subprocess or importlib")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in BANNED_CALLS:
                err(path, node.lineno, "call to %s() is not allowed" % node.func.id, "remove it; dynamic code can bypass the oracle")
        if module in LAYERS:
            rank = LAYERS.index(module)
            for dep in sibling_imports(tree):
                if dep in LAYERS and LAYERS.index(dep) >= rank:
                    err(path, 1, "layer violation: '%s' imports '%s'" % (module, dep),
                        "dependencies only point down: " + " < ".join(LAYERS) + " (see ARCHITECTURE.md)")


def check_docs() -> None:
    agents = os.path.join(ROOT, "AGENTS.md")
    if not os.path.exists(agents):
        err(agents, 0, "AGENTS.md is missing", "restore it from git history")
        return
    text = open(agents).read()
    if text.count("\n") + 1 > AGENTS_MAX_LINES:
        err(agents, 1, "AGENTS.md is longer than %d lines" % AGENTS_MAX_LINES,
            "keep AGENTS.md a table of contents; move detail into docs/ and link to it")
    for target in re.findall(r"\]\(([^)#\s]+)", text):
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        if not os.path.exists(os.path.join(ROOT, target)):
            err(agents, 1, "broken link: %s" % target, "fix the path or remove the link")


def main() -> int:
    check_source()
    check_docs()
    if errors:
        print("\n".join(errors))
        print("\n%d lint error(s)" % len(errors))
        return 1
    print("lint OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
