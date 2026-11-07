# Known weaknesses of the harness

- **Reward hacking**: an agent could special-case literal inputs. Mitigations: fresh random seed per verify
  run, corpus ratchet, lint bans on `re`/`eval`. Not airtight; review merged PRs occasionally.
- **Oracle quirks**: level 9 depends on CPython 3.12 behaviour. CI pins 3.12; do not bump it casually.
- **Throughput**: one issue in flight at a time. Raise only if the free request quota allows.
- **Agent CLI config**: how the Kilo CLI is given provider/model headlessly is unverified (see README).
- **Secrets**: the agent step can read `LLM_API_KEY`. Use a free-tier key with nothing else attached.
- **Doc gardening**: the article's recurring doc-cleanup agent is not built yet. Candidate next workflow.
