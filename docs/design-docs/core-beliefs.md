# Core beliefs

1. Humans steer, agents execute. Humans change the harness; agents change the engine.
2. The repository is the system of record. If the agent cannot read it here, it does not exist.
3. The oracle decides, not the agent. Success means `tools/verify.py` passes in a job that holds no API key.
4. Enforce invariants, not implementations. Lints and tests fix boundaries; inside them the agent is free.
5. Error messages are instructions. Every lint and fuzz failure says how to fix it.
6. A fixed failure stays fixed. Every solved case goes into `tests/corpus.jsonl`.
7. One thing in flight. One issue is worked at a time, which keeps free-tier request use predictable.
