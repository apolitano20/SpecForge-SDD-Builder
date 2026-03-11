# SpecForge — Improvement Worklog

## Quick Wins

- [x] **Add GitHub Actions CI** — No CI exists. Set up a simple pytest workflow on push to catch regressions.
- [x] **Add example JSON to Architect prompt** — The prompt defines the schema but gives no example output. A small example reduces hallucinations (empty fields, wrong structure).
- [x] **Validate Perplexity key upfront** — If research toggle is on but `PERPLEXITY_API_KEY` is missing, it crashes mid-run. Check at startup.
- [x] **Pin dependency ranges** — All deps use `>=` with no upper bound. A breaking `langgraph` 0.3.x release could silently break installs.

## Medium Effort

- [x] **Live spec preview during HITL** — When paused for user input, users see the challenge but can't see the current draft. A sidebar preview would make decisions easier.
- [x] **Cost/token tracking** — Each run is 4-10+ LLM calls with no visibility into token spend. Add a running counter to the dashboard and CLI.
- [ ] **Quality metrics dashboard** — Show why verification happened early (e.g., "Verified after 2 rounds: 0 critical issues, 8 total addressed, 3 user clarifications. Quality: 94/100"). Helps users assess if they want manual re-runs.
- [ ] **Deep review mode toggle** — Add `review_mode: thorough` config option. In thorough mode, Reviewer never verifies before round 5 and is prompted to be extra critical. Opt-in for users who want more scrutiny.
- [ ] **Stronger Reviewer validation** — Reviewer doesn't check if tech_stack items are used by components, or if external_actors match information_flows. Gaps lead to incoherent specs.
- [ ] **CLI progress output** — With `--no-hitl`, the CLI runs silently for 30-90 seconds. Add iteration/stage progress.

## Larger Features

- [ ] **Spec versioning / rollback** — If a HITL answer makes things worse, there's no undo. Snapshot state per iteration to enable "go back to round N."
- [ ] **Re-trigger research mid-debate** — Research runs once at the start. If the Architect pivots tech stack in round 3, stale research can mislead.
- [ ] **E2E smoke test** — All 162 tests mock LLM responses. A nightly test against a canned idea with real LLM calls would catch prompt/schema drift.
