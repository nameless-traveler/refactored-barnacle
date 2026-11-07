#!/usr/bin/env python3
"""Print the solver agent's prompt for one issue: python tools/build_prompt.py <issue-number>"""
import json
import subprocess
import sys

number = sys.argv[1]
issue = json.loads(subprocess.run(["gh", "issue", "view", number, "--json", "title,body"],
                                  capture_output=True, text=True, check=True).stdout)
case_line = next((ln[6:] for ln in issue["body"].splitlines() if ln.startswith("CASE: ")), "")

print("""You are the solver agent for this repository. Work only inside the repository checkout.

1. Read AGENTS.md first, then follow its pointers as needed. It is a map, not a manual.
2. Fix GitHub issue #%s (below) so the engine agrees with Python's re.
3. Reproduce first:  python tools/fuzz.py --case '%s'
4. Append the failing case as one JSON line {"pattern": ..., "text": ..., "level": ...} to tests/corpus.jsonl.
5. Finish only when `python tools/verify.py` prints VERIFY OK. If it fails, read the FIX lines and iterate.
6. Do not edit protected paths (harness/protected.txt). Do not run git commit or git push; the harness does that.
7. Update docs/exec-plans/active/feature-ladder.md if you finished a level's feature.

Issue title: %s

Issue body:
%s
""" % (number, case_line, issue["title"], issue["body"]))
