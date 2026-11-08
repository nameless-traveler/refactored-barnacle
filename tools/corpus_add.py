#!/usr/bin/env python3
"""Harness-owned ratchet: append the issue's own case to tests/corpus.jsonl (idempotent).
Usage: python tools/corpus_add.py case.json
"""
import json
import os
import sys

path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests", "corpus.jsonl")
case = json.load(open(sys.argv[1]))
text = open(path).read() if os.path.exists(path) else ""
for line in text.splitlines():
    if line.strip() and (json.loads(line)["pattern"], json.loads(line)["text"]) == (case["pattern"], case["text"]):
        print("case already in corpus")
        sys.exit(0)
with open(path, "a") as fh:
    if text and not text.endswith("\n"):
        fh.write("\n")
    fh.write(json.dumps({"pattern": case["pattern"], "text": case["text"], "level": case.get("level", 10)}) + "\n")
print("case added to corpus")
