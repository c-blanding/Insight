# Taskline planted bugs (spoiler — for humans only)

Do not feed this file to the QA agent. Use it to score whether the agent reproduced the bug and correctly identified the underlying cause.

| # | Area | Symptom | Root cause |
|---|---|---|---|
| TL-01 | Task persistence | Edited task description reverts after refreshing | `save()` replaces edited descriptions with their original seed values before writing to `localStorage` |
| TL-02 | Due-date sorting | November dates appear before October dates when sorting ascending | `visible()` uses `localeCompare()` on formatted date strings instead of comparing actual ISO dates |
| TL-03 | Combined filters | Ethan Zins + Done shows 6 tasks instead of 2 | Assignee and status filters use logical OR instead of AND |
| TL-04 | Task editing | Changing priority and clicking Cancel still saves the change | Priority change handler immediately mutates the task and calls `save()` |
| TL-05 | Due-date editing | Saving Nov 5 changes the date to Nov 4 | `finishEdit()` subtracts one UTC day when an existing task's due date changes |
| TL-06 | Pagination | Next and Previous change the page indicator but display the same five tasks | `pageItems()` always uses offset `0` instead of calculating the correct page offset |
| TL-07 | Drag-and-drop | Task visually moves columns, but its actual status remains unchanged | Drop handler updates `boardStatus` without updating `status` |
| TL-08 | Bulk archive | Selecting one task and archiving it archives all 12 tasks | Bulk handler processes `visible()` rather than only selected task IDs |
| TL-09 | Dashboard statistics | Archiving a completed task doesn't update Total or Completed counts | `renderMetrics()` includes archived records when calculating project statistics |
| TL-10 | Clear filters | Clear Filters resets other filters but leaves Assignee selected | Filter reset handler never clears `owner-filter` |
| TL-11 | Keyboard controls | Pressing Escape doesn't immediately close the task editor | Dialog's `cancel` event calls `preventDefault()`, suppressing native Escape dismissal |
| TL-12 | Cross-tab synchronization | Changes in one browser tab don't appear in another until refresh | The `storage` event listener is empty and doesn't reload or render updated data |

## Suggested verification order for agents

1. Reset demo data before each independent test.
2. Reproduce the bug using UI interactions only.
3. Compare expected and observed behavior.
4. Capture screenshots, browser console messages, and relevant evidence.
5. Record whether the bug was reproduced, not reproduced, or uncertain.
6. Evaluate root-cause accuracy separately when source-code inspection is allowed.
7. Do not provide the planted-bug answer key or scoring files to the agent.