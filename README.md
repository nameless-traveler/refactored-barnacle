# harness-regex

An experiment in "harness engineering": agents write a regex engine, a deterministic oracle
(CPython's `re`) decides whether they are right, and GitHub Actions runs the loop with your laptop off.

## The loop
```
finder (cron every 6h, no LLM)  -- fuzz vs re --> failure? --> files ONE issue --> dispatches solver
solver: [agent job, has API key] -> [verify job, fresh VM, no key] -> [merge] -> dispatches finder
clean at this level? finder raises harness/level.txt by one and keeps going (levels 1..10)
```

## Setup (about 10 minutes)
1. Create a **public** GitHub repo and push this folder to `main`.
2. Settings -> Actions -> General -> Workflow permissions: **Read and write**, and tick
   **Allow GitHub Actions to create and approve pull requests**.
3. Settings -> Actions -> General: require approval for workflows from outside collaborators.
4. Settings -> Secrets and variables -> Actions: add `LLM_API_KEY`.
5. Run `python tools/verify.py` locally once (stdlib only; it should fail on the stub engine, that is expected).
6. **Test the agent step first**, before trusting the loop: see "Not verified" below.
7. Actions tab -> finder -> Run workflow. It files issue #1 and dispatches the solver.

Outsiders: nothing runs from issues. Only `workflow_dispatch` starts the solver, which needs write access.
Anyone can still open issues on a public repo; GitHub's interaction limits can restrict that for up to 6 months at a time.

## Controls
- Kill switch: commit an empty file `harness/PAUSE`.
- Cap: `MAX_SOLVER_RUNS_PER_DAY` (default 20). One issue in flight at a time.
- Scheduled workflows in a public repo are disabled after 60 days with no repo activity.

## Not verified (test these first)
- How the Kilo CLI gets its provider/model headlessly. `tools/run_agent.sh` is the only place to change;
  swap in any agent that reads a prompt file and edits the repo.
- That your chosen model follows tool-call loops reliably. Try one issue by hand before enabling the cron.
- The workflow YAML parses, but it has never run on GitHub.
