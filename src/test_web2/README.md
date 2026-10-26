# Taskline test web app

An intentionally buggy **multipage** task-management website for Insight AI / Playwright QA. This is the second test application, covering task state and workflow issues beyond LumenShop's storefront tests.

## Run locally

Requires Python 3 and a modern browser. No npm install, database, API keys, or external assets are needed.

From this directory:

```bash
python -m http.server 5501 --bind 127.0.0.1 --directory test_web
```

On Windows, `py -3` can replace `python`. You can also double-click `start-windows.bat`.

Open **http://localhost:5501/**. Keep the terminal open; press Ctrl+C to stop.

Use port 5501 for Taskline and 5500 for LumenShop so they can run together. Always use the same hostname: localhost and 127.0.0.1 have separate browser storage. If Playwright runs in another container or machine, localhost refers to that environment; use your team's established reachable test-server address instead.

Serve `test_web`, not this parent directory. The parent includes human-only scoring material.

## Pages

These are separate HTML documents with real links and browser history, not views inside a single page.

| Path | Purpose |
|---|---|
| `/` or `/index.html` | Project board, status columns, drag and drop |
| `/tasks.html` | All tasks, sortable/filterable list and pagination |
| `/my-tasks.html` | Ethan’s assigned tasks |
| `/archive.html` | Archived tasks and restore actions |
| `/task.html?id=2` | Direct-linkable details for task 2 |
| `/task.html?new=1` | New-task flow on the task page |

Task titles open their detail page. **Quick edit** on the board (or **Edit** beside a list title) opens the editor without navigating. On the detail page, choose **Edit task** to change fields. This retained dialog supports the keyboard-dismissal test.

Filters and pagination are encoded in the current page URL. The detail page’s **Back to tasks** link restores the originating URL, including filters. Browser Back/Forward is supported. Separate documents read the same browser-local task data; the intentional live cross-tab synchronization defect remains. The original 12 planted defects remain enabled.

## Features

- Four-column task board: To do, In progress, In review, Done.
- List view with five tasks per page.
- Task creation and editing, assignees, priority, category, due date, descriptions.
- Drag tasks between columns; status can also be edited in task details.
- Search, assignee/status/priority filters, title and date sorting.
- Task selection and bulk archive/restore.
- My tasks (Ethan Zins), Archive, project summary counts.
- Browser-local persistence and resettable fixture data.

Some of these features deliberately behave incorrectly. This is a test fixture, not production software. There are no network/API failures planted in this app. It makes no external requests, has no authentication, and sends no task data to a server.

## Files

```text
Taskline/
  README.md
  start-windows.bat
  agent-inputs.json
  human_only/
    BUGS.md
    scorecard.csv
    VERIFICATION.md
  test_web/
    index.html
    tasks.html
    my-tasks.html
    archive.html
    task.html
    assets/
      styles.css
      data.js
      app.js
```

`test_web` is the only directory that should be served. `human_only` is for evaluators, not the QA agent. Source code naturally contains implementations of the defects; restrict the agent to the browser if testing UI-only discovery.

## Test setup

1. Start the local server and open http://localhost:5501/.
2. Click **Reset demo data** at the bottom, then accept the confirmation. This restores 12 tasks, clears filters and selection, and navigates to index.html. Reset works from every page.
3. Navigate to the case’s URL after resetting. Use one case from `agent-inputs.json` as the graph's `url`, `bug_description`, and `expected_behavior`.
4. Reproduce with visible UI actions. Capture observed versus expected behavior and relevant evidence. Do not fix code during a run.
5. Reset before the next independent case. Tests that use multiple tabs must share one browser context. Close extra tabs before resetting for the next case.

Do not supply `auth_profile_id`: there is no sign-in. Local storage is demo state, not an authenticated session.

The fixed October/November 2026 dates are intentional repeatable fixtures. No planted behavior depends on today's date, a network timeout, or the user's timezone. Browser storage is shared by tabs of the same origin in the same browser context; use a new context for isolated runs.

## Agent-facing sample inputs

`agent-inputs.json` contains 12 independent reports with UI setup/reproduction instructions and expected behavior, but no implementation explanations. Give the agent one case at a time when measuring reproduction. For unprompted discovery, give only the app URL and the feature list above; omit the sample reports as well.

Examples include descriptions reverting after reload, filters failing in combination, date sorting, Cancel committing a priority change, and page two repeating page one.

## Scoring

Use `human_only/BUGS.md` and `human_only/scorecard.csv` yourself. Do not feed either to Insight. For UI-only runs, score reproduction and evidence separately from a root-cause hypothesis. A UI symptom alone does not prove an exact code-level root cause.

## Reset and storage

The reset button affects only the `taskline-demo-v1` key on this origin. Browser storage failures show a notice; that is environmental behavior, not a planted defect. Data is local to the browser and is not shared with other people. The buggy write behavior is part of the test set; see the private answer key.
