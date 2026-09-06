# Validation notes

The upgraded full-stack app restored the Editorial Study Desk shell without visible regressions. The student preview shows the Import syllabus action, the existing Pomodoro hierarchy, and the focus-room anchor at desktop width. The parent preview at `/?view=parent` shows the Download report control, KPI cards, weekly focus chart, and the TableTot insight illustration with correct contrast. The project type-check and production build are passing; remaining workflow validation is focused on upload mutation, PDF download, and responsive control behavior.

The mobile student preview keeps the Import syllabus action visible above the focus room, while the mobile parent preview keeps Download report and learner selection side by side without clipping. KPI cards remain readable in a two-column layout, and the focus chart remains legible below the fold.

The syllabus modal now presents a clear upload target and the focus settings panel visibly exposes Quiet, Rain, Café, and Forest ambience choices, volume control when enabled, and Paper, Dusk, and Meadow themes. Both surfaces preserve the cream/navy/coral planner language and remain readable at desktop width.

A live localhost tRPC call with a sample text syllabus succeeded end to end: the server accepted the base64 upload, stored the source, invoked the built-in structured model, and returned three normalized assignment objects with subject, priority, confidence, and stable IDs. The returned response was saved to `syllabus-e2e-response.json` for debugging provenance.

The live browser opened the syllabus modal successfully, and DOM inspection confirmed one hidden file input accepting PDF, TXT, Markdown, and CSV uploads. The modal presented its persistent title, upload target, and action buttons as expected.

In-browser upload was exercised with the sample syllabus via the live file input. The modal accepted the file, the Find assignments action changed to Reading syllabus…, and the persistent loading banner appeared. The AI request remained pending during the initial browser refresh, so the next step is to inspect the server response and complete approval if it returns.

The live browser workflow completed successfully: the AI review displayed three extracted assignments with subjects, due dates, confidence, and priority; approving them showed a success toast and inserted all three Syllabus-tagged tasks at the top of the student task list, increasing the list from 4 to 7 items.

The live parent dashboard export was triggered successfully. The browser showed the “Weekly progress report downloaded” confirmation toast after clicking Download report, and the generated filename is `tabletot-weekly-progress-aarav.pdf`.

The live focus room interaction also passed: selecting Rain exposed the volume control and changed the room status to “Rain on”; switching to Meadow changed the focus-room surface while the timer stayed stable at 24:18. This confirms sound and visual theme changes do not reset the session.

The student dashboard now presents the selected task directly inside the focus room: the initial unfinished task loads automatically, its title appears in the timer and Now working on panel, and the room exposes Mark complete. The dedicated focus settings remain embedded above the timer, so task context and concentration controls stay in one workspace.

The live task list exposes Focus buttons on task rows. The attempted click targeted an already-completed mathematics task, which remained unavailable and did not replace the active Biology focus context; this is the intended guard against starting focus on completed work. The page scrolled to the task list as part of the handoff interaction.

The live student workspace confirms unfinished task rows expose Focus actions and the focus room keeps the selected task context visible while the timer remains controllable. Completed tasks are disabled from starting a new focus block, and the shared room remains usable after interacting with the task list.

After the layout recomposition, desktop shows the Pomodoro focus room and Today’s rhythm task list as adjacent columns with a clear Task → focus → reset bridge. The mobile preview stacks the same workspace cleanly: the focus room remains the primary anchor and the task column follows without clipping.

Final browser verification passed end to end. The unfinished task “Read chapter 4 + annotate” was activated through its Focus action; the Pomodoro timer and Now working on panel updated to that task and its English subject. Clicking Mark complete in the focus room produced the success toast, changed Tasks complete from 1/7 to 2/7, and moved the selection to the next unfinished task “Lab reflection (finish and submit)”.

Completion-state confirmation passed: the completed “Read chapter 4 + annotate” row has class task-row--done and its Focus button is natively disabled. Fresh desktop and mobile previews after the verification show the integrated student workspace remains responsive and visually stable.
