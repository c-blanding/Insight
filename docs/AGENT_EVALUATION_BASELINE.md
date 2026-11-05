# Browser QA Agent Evaluation Baseline

## Purpose

This benchmark measures the agent’s current behavior before changing planning, execution, verification, or report logic. The cases use the controlled LumenShop fixture. The case labels and planted-bug catalog are evaluator-only; the runner sends only the target URL, bug description, and expected behavior to the agent.

## Run it

Start LumenShop in one terminal:

```powershell
python -m http.server 5500 --directory src/test_web
```

Start Playwright MCP in another terminal:

```powershell
.\scripts\start-playwright-mcp.bat
```

Set the local target policy in PowerShell, then run the benchmark:

```powershell
$env:INSIGHT_LOCAL_TARGETS = "localhost,127.0.0.1,::1"
uv run python -m insightai.evaluation --base-url http://localhost:5500 --output evals/agent_qa/results/baseline.json
```

Use `--repeat 3` for three fresh runs of each selected case. A single run is a smoke baseline, not a reliability estimate.

The default benchmark excludes the interactive login case. To exercise it, run in an interactive terminal:

```powershell
uv run python -m insightai.evaluation --base-url http://localhost:5500 --include-login --interactive-login --output evals/agent_qa/results/baseline-with-login.json
```

The runner creates a fresh agent/checkpointer and unique thread ID per case, executes cases serially, counts model-visible Playwright tool invocations, and records aggregate metrics. It does not store prompts, full browser snapshots, reports, credentials, or storage-state data in the result file. Artifact references are included only when the run has them.

## Metrics

- **Verdict accuracy:** correct expected verdicts among scored cases.
- **Bug reproduction rate:** known-bug cases with a `bug_confirmed` verdict, required path/tool evidence, and at least one observable finding.
- **False-positive rate:** bug-confirmed verdicts among no-bug and inconclusive cases.
- **Correct inconclusive rate:** inconclusive verdicts among cases labeled inconclusive.
- **Evidence support rate:** eligible definitive-verdict reports with observable evidence and a heuristic step-number or artifact-key reference in the report.
- **Average tool calls / duration:** arithmetic mean across completed cases; failed runs are excluded from quality and efficiency denominators.
- **Login recovery rate:** successfully continued login cases among cases where interactive login was actually attempted. It is `null` when no login case was attempted.

`path_markers` and report citation matching are deliberately simple string heuristics. They are useful for a first baseline, not a substitute for human review. Treat the small fixture benchmark as a regression signal, not a claim about general website coverage. Re-run cases in more than one trial before making claims about reliability.

## Baseline result

**Status: blocked on 2026-11-05.** This environment has the model API key configured, but the pinned Playwright MCP startup could not resolve its npm dependency (`ETARGET: no matching version found for playwright-core@1.65.0`), and MCP never opened port 8931. No agent scores are reported. Run the command above after the browser service starts, inspect the JSON result, then record the metrics and environment below. Do not enter credentials in benchmark cases or commit secrets.

| Metric | Baseline |
|---|---:|
| Cases scored | Not measured |
| Verdict accuracy | Not measured |
| Bug reproduction rate | Not measured |
| False-positive rate | Not measured |
| Correct inconclusive rate | Not measured |
| Evidence support rate | Not measured |
| Average tool calls | Not measured |
| Average duration | Not measured |
| Login recovery rate | Not measured in default run |

Record the date, commit SHA, model name, number of repetitions, and any excluded cases when filling this table.
