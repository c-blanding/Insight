# Insight AI Agent Improvement Plan

## Objective

Improve the browser QA agent so it can investigate user-supplied websites reliably, support its conclusions with inspectable evidence, recover correctly from login interruptions, and demonstrate its performance with repeatable evaluations. Extend the agent with read-only Sentry and GitHub context so it can connect a reproduced browser problem to likely code at the exact deployed revision. This plan covers the agent and its evaluation artifacts. The separate backend/API handoff remains outside this scope.

## Current foundation

- LangGraph separates planning, per-step execution, login handling, and report finalization.
- Pydantic models define plans, findings, reports, artifacts, and timelines.
- Playwright MCP provides browser actions, snapshots, screenshots, console/network capture, and video.
- Login can interrupt a run and save an encrypted browser profile.
- Target policy currently requires preconfigured host lists and checks explicit navigation targets. This conflicts with the product flow where a client supplies the URL at run time.
- The current report contains a browser verdict and prose but has no typed source diagnosis or Sentry incident context.
- Playwright MCP is already integrated as a dynamic browser tool provider; Sentry and GitHub MCP tools are not yet part of the graph.

## Scope decisions

- A user may enter any valid HTTP or HTTPS public URL; the product must not require a preapproved public-host list.
- The URL is unknown until run time, so policy decisions happen at runtime.
- Local/private-network testing should be supported only through an explicit authorization/configuration path. Browser egress enforcement for redirects and subresources belongs at the runtime/backend boundary and must be coordinated with the backend owner; this plan does not implement the backend service.
- Prioritize agent correctness and measurable senior-design results over a new frontend, accounts, billing, or deployment platform.

## Success measures

Report these for each evaluation run and for the overall benchmark:

- **Reproduction rate:** known seeded bugs reproduced with sufficient evidence / seeded bug cases.
- **False-positive rate:** bug-confirmed verdicts on cases where the bug is absent.
- **Correct inconclusive rate:** ambiguous or blocked cases correctly reported as inconclusive.
- **Evidence support rate:** report claims linked to a step and observable evidence.
- **Execution efficiency:** tool calls and elapsed time per case.
- **Login recovery rate:** interrupted cases that continue and complete successfully.

Capture a baseline before setting final quality thresholds. Changes should improve correctness without unacceptable regressions in time or tool use.

## Architecture decisions

- Keep LangGraph as the agent orchestrator and retain typed state/domain models.
- Make the plan and each step carry an observable completion condition; execution should verify it before marking a step complete.
- Treat browser evidence as the source for verdicts. Reports should cite step numbers and evidence references and use `inconclusive` when the evidence is insufficient.
- Keep URL acceptance separate from network safety: accept arbitrary public destinations, validate user input at run time, and require runtime-level egress controls for redirects and all browser requests.
- Keep checkpointer injection supported. Agent tests should cover same-process pause/resume; durable cross-worker recovery remains a backend/runtime integration requirement.
- Keep Sentry and GitHub access in a dedicated, read-only investigation stage. Use MCP-provided tools for model-directed lookup, but keep the graph responsible for sequencing, validated context, and final report structure.
- Pin source analysis to the GitHub commit corresponding to the tested deployment. Credentials are resolved by integration configuration and never enter graph state, prompts, or tool arguments.
- Make Sentry context and source diagnosis optional so browser-only runs remain supported. Keep webhook intake, automatic event triggering, GitHub writes, and FastAPI implementation out of this phase.

## Task list

### Phase 0: Establish an agent evaluation baseline

1. **Create a labeled browser QA benchmark.** Assemble a small deterministic set from LumenShop and other controlled pages: known bugs, bug-absent cases, and cases that should end inconclusive. Record the expected path, expected observation, and correct outcome for each.
2. **Add a benchmark runner and result format.** Record case ID, agent verdict, whether the key path was reached, evidence references, tool calls, duration, and error category. Keep secrets and raw auth state out of results.
3. **Run and document the baseline.** Report reproduction rate, false positives, correct inconclusive rate, evidence support, execution efficiency, and login recovery where applicable.

**Checkpoint:** The benchmark can be rerun and produces a comparable summary without changing application code between cases.

### Phase 1: Accept runtime URLs safely

4. **Replace the public hostname allowlist requirement.** Allow any syntactically valid user-supplied HTTP/HTTPS public URL. Continue to reject malformed URLs, embedded credentials, unsafe schemes, and destinations resolving to private or non-routable addresses unless private-target access has been explicitly authorized.
5. **Define the browser egress contract with the backend/runtime owner.** Specify how redirects, link clicks, frames, and subresource requests are restricted. The agent-side URL check alone cannot enforce policy after Chromium starts loading a page.
6. **Add target-policy tests.** Cover arbitrary public hosts, malformed URLs, credentials, unsafe schemes, DNS resolving to prohibited addresses, and the explicit private-target authorization path.

**Checkpoint:** A previously unknown public URL can be tested without configuration changes, while unsafe destinations are rejected at the agreed runtime boundary.

### Phase 2: Make plans and step completion verifiable

7. **Tighten the plan contract.** Require a bounded, non-empty sequence of browser actions. Each step should include the behavior to observe that would show whether the step succeeded.
8. **Verify each step before advancing.** After an action, capture a fresh observation and compare it with the step’s completion condition. If the condition is not met, make one bounded recovery attempt or record the specific blocker; do not mark the step complete just because the tool call returned.
9. **Add execution-flow tests.** Cover malformed plans, successful steps, failed actions, bounded recovery, tool-budget exhaustion, and preservation of incomplete state.

**Checkpoint:** The agent distinguishes “action executed” from “test step verified,” and the run terminates with a clear reason when a step cannot be verified.

### Phase 3: Ground reports in evidence

10. **Improve finding structure.** Separate observed behavior, expected behavior, verification result, and evidence references in the typed finding model.
11. **Enforce verdict rules.** `bug_confirmed` requires evidence supporting the reported behavior; `not_reproduced` requires the relevant path to have completed; blocked or ambiguous cases remain `inconclusive`.
12. **Test report quality against labeled cases.** Check verdict correctness and ensure each material report claim points to a step and evidence item. Add regression cases for contradictory or incomplete findings.

**Checkpoint:** A reviewer can trace each verdict to the relevant browser observations, and insufficient evidence cannot produce a confident positive or negative conclusion.

### Phase 4: Prove login interruption and recovery

13. **Add lifecycle tests for login pause, continue, and cancel.** Verify the same thread resumes at the interrupted point, the browser session remains available while paused, and cancellation reaches a terminal state with cleanup.
14. **Verify credential boundaries.** Confirm passwords and raw storage state never enter graph inputs, resume payloads, logs, or evaluation outputs; only encrypted saved profiles cross the persistence boundary.
15. **Document checkpointer expectations.** Demonstrate same-process resume with the supported checkpointer and clearly document that worker restart recovery requires a shared checkpointer plus a browser recovery/ownership strategy supplied by the runtime/backend.

**Checkpoint:** The full login path is repeatable, credential boundaries are tested, and the runtime dependency for durable recovery is explicit.

### Phase 5: Measure and refine

16. **Run the benchmark after each agent change.** Compare results to the Phase 0 baseline and inspect failures by category: planning, action selection, verification, auth, browser/runtime, or reporting.
17. **Improve the weakest measured failure category.** Make focused changes and add each discovered failure as a permanent regression case.
18. **Publish senior-design results.** Include the evaluation set, method, metrics, limitations, representative successful/failed traces, and a comparison with a non-agent or earlier baseline if available.

**Final checkpoint:** The evaluation is repeatable, the agent’s limitations are explicit, and the final report supports its claims with measured results and traceable evidence.

### Phase 6: Add read-only source diagnosis with GitHub MCP

19. **Define typed investigation context and diagnosis output.** Add optional Sentry issue/event references and GitHub repository plus immutable commit SHA to validated agent input/state. Add a structured source diagnosis model with summary, candidate locations, line references, commit SHA, confidence, and supporting browser/Sentry evidence. Credentials must not be accepted as input.
   - **Acceptance:** Existing browser-only input remains valid; integration IDs and repo/ref are validated; secret-like values are rejected; diagnosis has typed source references and an explicit confidence/unknown state.
   - **Verification:** Unit checks cover optional/partial context, invalid refs, secret-key rejection, and serialization round trips.
   - **Dependencies:** None. **Likely files:** `utils/states.py`, `utils/objects.py`, `agent.py`, contract tests. **Scope:** Medium.
20. **Connect a minimal read-only GitHub MCP toolset.** Expose only the repository lookup, code search, commit lookup, and file-content tools needed for diagnosis. Bound result sizes and require every code lookup to use the supplied commit SHA.
   - **Acceptance:** The diagnosis stage can fetch repository metadata and search/read files at an immutable SHA; no write tools are exposed; results are size-limited and include path + revision metadata.
   - **Verification:** MCP adapter tests use a fake server/client and assert tool allowlisting, SHA propagation, bounded output, and graceful unavailable-server errors.
   - **Dependencies:** Task 19. **Likely files:** `mcp_clients/github.py` (or equivalent), configuration, integration tests. **Scope:** Medium.
21. **Add an evidence-guided diagnosis stage.** After browser execution, create a structured browser assessment; when repository context is present, pass that assessment and findings to a dedicated source diagnosis node before final report synthesis. Skip source diagnosis cleanly when no repository is supplied or GitHub is unavailable.
   - **Acceptance:** Browser verdict is determined independently; diagnosis consumes browser assessment and pinned source context; absent GitHub context preserves the current browser-only path; tool failure does not erase QA findings.
   - **Verification:** Graph tests cover the optional branch, cited candidate locations, revision mismatch, tool failure, and unchanged browser verdict.
   - **Dependencies:** Tasks 19–20 and Phase 3 evidence structure. **Likely files:** `utils/nodes.py`, `utils/edges.py`, `agent.py`, prompts, graph tests. **Scope:** Medium.

**Checkpoint:** A browser-only run still works; a run with repository and commit context can produce read-only, commit-pinned candidate code locations tied to browser evidence.

### Phase 7: Add optional Sentry context to investigations

22. **Connect scoped, read-only Sentry MCP tools.** Allow the agent to load the supplied issue/event and relevant trace context. Normalize and redact the useful fields before they enter graph state; do not expose broad project administration or write tools.
   - **Acceptance:** A supplied issue/event reference returns a bounded, sanitized context summary; no Sentry write/admin tools or access tokens are visible to the model; missing context is a supported state.
   - **Verification:** Fake MCP responses cover issue/event/trace success, redaction, empty results, and connection/auth failures.
   - **Dependencies:** Task 19. **Likely files:** `mcp_clients/sentry.py` (or equivalent), state/context models, configuration, integration tests. **Scope:** Medium.
23. **Combine observations and diagnosis in the final report.** Preserve the browser verdict as the source of reproduction status. Present source locations as hypotheses with confidence and supporting evidence; keep unavailable or mismatched Sentry/GitHub context explicit and non-fatal to the browser report.
   - **Acceptance:** Structured report contains browser verdict and optional source diagnosis; citations identify commit/path/lines; diagnosis cannot upgrade an inconclusive browser verdict to bug-confirmed; integration failures remain visible but do not discard browser output.
   - **Verification:** Report model and graph tests cover no integrations, each provider alone, both providers, contradictory context, and incomplete browser evidence.
   - **Dependencies:** Tasks 21–22. **Likely files:** `utils/objects.py`, `utils/states.py`, report node/prompt, result serialization tests. **Scope:** Medium.
24. **Add integration evaluation cases.** Cover a known browser bug with matching source at a pinned commit, a Sentry event with useful stack/trace context, absent integrations, and integration lookup failures. Compare the report’s citations and diagnosis against labeled expected results.
   - **Acceptance:** Benchmark reports source-location accuracy, evidence support, and degradation behavior when an integration is unavailable; results remain comparable to the browser-only baseline.
   - **Verification:** Run the integration benchmark with mocked Sentry/GitHub tools and at least one controlled live end-to-end case when credentials are configured.
   - **Dependencies:** Tasks 19–23. **Likely files:** evaluation cases/runner and documentation. **Scope:** Medium.

**Final integration checkpoint:** The agent can accept optional Sentry and GitHub context on a manually started run, reproduce the issue, inspect the exact source revision, and return a report that separates observed behavior from likely cause.

## Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Evaluation cases are too easy or too similar to LumenShop | Inflated performance estimate | Include varied page layouts, bug types, and non-bug/ambiguous cases; document case selection. |
| LLM verdicts remain subjective | False bug reports or missed bugs | Use explicit expected observations and report rules; score against human-labeled outcomes. |
| Arbitrary URLs create SSRF exposure in hosted execution | Access to unintended internal services | Coordinate runtime network egress enforcement; test redirects and subrequests, not only initial URLs. |
| Browser/model nondeterminism makes results noisy | Weak comparisons across changes | Repeat cases where practical, record model/config, and report variance and failures. |
| Backend durability assumptions exceed agent control | Resume fails after process/worker loss | Keep the integration boundary explicit and test only the guarantees provided by each configured runtime. |
| Source diagnosis overstates a likely cause as confirmed | Misleading code guidance | Keep browser verdict and code hypothesis separate; require source citations and confidence; allow an inconclusive diagnosis. |
| MCP returns excessive or untrusted repository/incident content | Prompt injection, token waste, or unsafe conclusions | Enable narrow read-only toolsets, cap results, treat fetched content as untrusted data, and do not expose write tools. |
| Tested deployment does not map to the supplied GitHub commit | Incorrect source references | Require and display an immutable commit SHA; report a revision mismatch instead of guessing. |

## Out of scope

- Building or owning the FastAPI service, user accounts, billing, or frontend.
- Implementing the backend team’s browser network sandbox or distributed worker scheduler.
- Sentry webhook ingestion, automatic event-triggered runs, or the FastAPI service.
- Creating GitHub issues/comments/PRs or changing source code.
- Adding mobile testing or a general-purpose browser automation product.
