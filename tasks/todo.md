# Insight AI Agent Improvement Tasks

## Phase 0: Evaluation baseline

- [x] Create a labeled benchmark with seeded bug, bug-absent, inconclusive, and login-recovery cases.
- [x] Add a runner and machine-readable results for verdict, path reached, evidence, tool calls, duration, and error category.
- [ ] Run the baseline and document the metrics defined in `tasks/plan.md`.

  **Blocked 2026-11-05:** Playwright MCP could not start because npm returned `ETARGET` for `playwright-core@1.65.0`; see `docs/AGENT_EVALUATION_BASELINE.md`. No baseline metrics were fabricated.

- [x] Evaluator unit tests pass (5 tests); existing source helper tests pass (23 tests).
- [x] CLI help and Python compilation checks pass.
- [ ] Capture and review a live agent baseline once Playwright MCP starts successfully.

### Checkpoint

- [ ] Benchmark is repeatable and produces a comparable summary.

## Phase 1: Runtime URL handling

- [ ] Allow arbitrary valid public HTTP/HTTPS target hosts without preconfiguration.
- [ ] Retain runtime validation for malformed URLs, credentials, unsafe schemes, and prohibited private destinations.
- [ ] Agree with backend/runtime owner on enforcement for redirects, links, frames, and subresources.
- [ ] Add target-policy tests, including DNS-to-prohibited-address behavior and private-target authorization.

### Checkpoint

- [ ] Unknown public URL works without allowlist edits; unsafe access is blocked at the agreed boundary.

## Phase 2: Verifiable plans and steps

- [ ] Make plans bounded, non-empty, and include observable step completion conditions.
- [ ] Verify each step from a fresh browser observation before advancing.
- [ ] Add bounded recovery and explicit blockers for unverified steps.
- [ ] Add tests for malformed plans, success, tool errors, retry limits, and state preservation.

### Checkpoint

- [ ] Step completion reflects verified behavior rather than successful tool invocation alone.

## Phase 3: Evidence-grounded reports

- [ ] Structure findings around observed behavior, expected behavior, verification, and evidence references.
- [ ] Enforce verdict rules for confirmed, not reproduced, and inconclusive outcomes.
- [ ] Add labeled report tests for supported, contradictory, and insufficient evidence.

### Checkpoint

- [ ] Verdict claims trace to steps and evidence; insufficient evidence yields inconclusive.

## Phase 4: Login lifecycle

- [ ] Test pause, continue, and cancel behavior, including session retention and terminal cleanup.
- [ ] Test that credentials and raw storage state stay out of graph state, logs, and evaluation artifacts.
- [ ] Document same-process and durable recovery guarantees by checkpointer/runtime configuration.

### Checkpoint

- [ ] Login flow is repeatable and its durability boundary is clear.

## Phase 5: Evaluation and presentation

- [ ] Re-run the benchmark after agent changes and add failures as regression cases.
- [ ] Improve the weakest measured failure category in focused iterations.
- [ ] Present the benchmark method, results, limitations, and representative traces for the senior design review.

### Final checkpoint

- [ ] Results are repeatable and claims are supported by metrics and evidence.

## Phase 6: GitHub-backed source diagnosis

- [ ] Define optional Sentry issue/event and GitHub repo/immutable-commit input fields plus a typed source-diagnosis result; reject credentials from graph input.
- [ ] Connect a minimal read-only GitHub MCP toolset for repo/commit lookup, code search, and file reads pinned to the supplied commit.
- [ ] Add a graph diagnosis stage that consumes browser assessment and findings, preserves the browser verdict, and skips cleanly when GitHub context or service is unavailable.

### Checkpoint

- [ ] Browser-only runs remain unchanged; repository-backed runs return candidate files/lines tied to browser evidence and the exact source commit.

## Phase 7: Sentry context and combined report

- [ ] Connect scoped, read-only Sentry MCP tools for issue, event, and trace context; normalize and redact data before adding it to graph state.
- [ ] Extend the structured final report with optional source diagnosis, commit/path/line citations, confidence, and explicit unavailable/mismatched-context status.
- [ ] Add integration benchmark cases for matching source, useful Sentry context, missing integrations, and provider failures.

### Final integration checkpoint

- [ ] A manually started agent run can use optional Sentry context, reproduce the issue, inspect the exact GitHub revision, and report browser observations separately from likely code causes.
- [ ] Sentry/GitHub credentials and write tools are not exposed to the model; existing browser-only runs remain supported.
