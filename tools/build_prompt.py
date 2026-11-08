#!/usr/bin/env python3
"""Print the solver agent's prompt for one issue: python tools/build_prompt.py <issue-number>
Exits quickly (before any model request) if the number is not a finder-created issue."""
import json
import subprocess
import sys

number = sys.argv[1]
issue = json.loads(subprocess.run(["gh", "issue", "view", number, "--json", "title,body"],
                                  capture_output=True, text=True, check=True).stdout)
case_line = next((ln[6:] for ln in issue["body"].splitlines() if ln.startswith("CASE: ")), "")
if not case_line:
    sys.exit("#%s has no 'CASE:' line, so it is not a finder-created issue (a PR number?). Nothing to do." % number)

print("""You are the solver agent for this repository. Work only inside the repository checkout.

1. Read AGENTS.md first, then follow its pointers as needed. It is a map, not a manual.
   If the issue kind is `timeout`, or the failing pattern has nested repeats, read docs/design-docs/matcher-design.md first.
2. Fix GitHub issue #%s (below) so the engine agrees with Python's re.
3. Reproduce first:  python tools/fuzz.py --case '%s'
4. Finish when `python tools/verify.py` prints VERIFY OK. It checks your issue's case passes and that you broke nothing
   that main already handled. Unrelated failures that main also has are NOT your job. Do not touch tests/corpus.jsonl;
   the harness records the case itself.
5. If an edit fails twice, re-read the file and rewrite the whole function (or file) with the write tool.
6. If verify is still failing after two serious attempts at different approaches, STOP and say what you learned.
   A stopped run costs less than a run that burns its whole time limit.
7. Do not edit protected paths (harness/protected.txt). Do not run git commit or git push; the harness does that.

Issue title: %s

Issue body:
%s
""" % (number, case_line, issue["title"], issue["body"]))
