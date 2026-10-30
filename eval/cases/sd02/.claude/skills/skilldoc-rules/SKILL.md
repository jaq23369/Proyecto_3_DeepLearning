---
name: skilldoc-rules
description: Add or change deterministic checks in src/deterministic_checks.py. Use when a new kind of problem can be verified without the LLM.
---

# Deterministic rules

1. Every rule returns `Finding` objects from `src/schemas.py` with `origin="rule"`.
2. A rule only marks a finding as `confirmed` when it can prove it; otherwise use `possible_conflict`.
3. Register the new rule in `run_all` at the end of `src/deterministic_checks.py`.
4. Uploads are limited by `MAX_FILES` (40 files) and `MAX_ZIP_BYTES` (10 MB) in `src/ingest.py`.
