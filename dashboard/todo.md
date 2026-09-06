# TableTot feature upgrade checklist

## Backend and architecture

- [x] Upgrade the static project to the full-stack web-db-user scaffold for server-side LLM access, file upload, and typed procedures.
- [x] Preserve the existing Editorial Study Desk UI and migrate the student and parent dashboard behavior without regressions.

## AI syllabus upload

- [x] Add a syllabus upload entry point to the student workspace.
- [x] Extract text from supported syllabus files and send it to the server-side built-in LLM.
- [x] Return structured assignment objects with title, subject, due date, priority, and confidence.
- [x] Add a review step so the student can approve or remove extracted assignments before they populate the to-do list.
- [x] Persist approved assignments and show clear loading, empty, and error states.

## Parent PDF report

- [x] Add a parent dashboard export control for the current weekly progress period.
- [x] Generate a readable PDF report containing focus time, streak, task completion, quiz average, subject balance, and privacy note.
- [x] Trigger a browser download with a meaningful filename and handle export failures gracefully.

## Pomodoro focus room

- [x] Add selectable ambient sound presets with play/pause and volume controls.
- [x] Add visual focus themes that affect the focus room without reducing text contrast.
- [x] Keep timer state and accessibility behavior stable while settings change.

## Validation and delivery

- [x] Run type checking and production build.
- [x] Verify syllabus extraction review, task population, PDF download, sounds, themes, and responsive layouts.
- [x] Save a delivery checkpoint and report any follow-up limitations honestly.

## Post-upgrade regression checks

- [x] Run dependency installation, type checking, and production build after the full-stack upgrade and restored UI files.
- [x] Verify the restored student and parent dashboards in the browser after the upgrade, including desktop and mobile interactions.

## Follow-up validation gaps

- [x] Add persistent empty and error messaging inside the syllabus upload modal instead of relying only on transient toasts.
- [x] Manually exercise syllabus upload, assignment approval, weekly PDF export, ambient sound, and visual theme controls in the browser.

## Student dashboard Pomodoro and to-do integration

- [x] Connect each student task row to the Pomodoro focus room as an explicit “Focus” action.
- [x] Show the selected task consistently in the focus room and keep task completion status synchronized with the dashboard.
- [x] Recompose the student layout so the to-do list and focus room feel like one connected daily workspace on desktop and mobile.
- [x] Validate task-to-focus handoff, timer stability, task completion, and responsive layouts.

## Remaining student workspace validation gaps

- [x] Rework the student dashboard layout so the task list and focus room share a visibly integrated workspace on desktop and mobile, not just linked actions across separate grids.
- [x] Manually verify that clicking Focus on an unfinished task updates the focus-room task context, then use Mark complete in the focus room and confirm task state syncs back to the list.
- [x] Capture fresh desktop and mobile validation for the integrated student workspace after the layout update.

## Final browser verification gap

- [x] In the browser, click Focus on a clearly unfinished task and confirm the Pomodoro card updates to that task title and subject.
- [x] From the focus room, click Mark complete on the selected task and verify the same task becomes completed or disabled in the task list.
- [x] Capture fresh desktop/mobile evidence after successful handoff and completion sync.

## Final completion-state confirmation

- [x] Confirm the task completed from the focus room has a completed row state and a disabled Focus control in the live task list.
- [x] Capture desktop and mobile previews after the completed-task state is visible.

## Task ordering, persisted progress, live parent status, and role login

- [ ] Add database tables for student profiles, ordered tasks, focus sessions, and active task progress.
- [ ] Add protected tRPC procedures for task listing, reorder, completion, focus start/pause/finish, and parent progress queries.
- [ ] Replace hardcoded Aarav/Meera identity with a student/parent login screen and session-backed profile display.
- [ ] Add keyboard-accessible drag-and-drop task reordering with a persistent order value.
- [ ] Persist focus session history and task completion events to the database.
- [ ] Show the actively focused task and elapsed progress in the parent dashboard with live polling updates.
- [ ] Validate login gating, task reorder persistence, focus history, task completion sync, parent live progress, and responsive layouts.
