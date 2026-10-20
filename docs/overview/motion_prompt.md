# 30-second Claude Motion overview — ready-to-use prompt

This is a `claude.ai` task (Claude Motion artifact), not something Claude Code can produce.
Steps (see `references/overview-video.md` in the `analytics-final-project` skill for the full
version):

1. Run a demo in the cloud for 15–30 minutes, so there are real results to show (needs
   Milestone 6 deployed first).
2. Screenshot: the live flow chart with an import held, the Models (MoE) swimlane, a step
   panel with SQL and a formula, a Release decision, the Analytics forecast, the filled BINGO
   card. (Local versions of the first four already exist in `docs/images/` from this session's
   demo — re-take them against the real cloud deployment for the actual video, since the prompt
   below says not to invent numbers; a deployed app's real data belongs in the final video.)
3. In a `claude.ai` chat, attach the screenshots and paste the prompt below. Ask for a Motion
   video.
4. Review by scrubbing the timeline; comment on anything that needs a change.
5. Export the MP4 to `docs/overview/overview.mp4`, plus a short GIF preview.
6. Drag the MP4 into the README editor on GitHub so it plays inline; keep the GIF as a fallback.

## The prompt, filled in

```text
Make a 30-second Motion video giving an overview of my data analytics final project.

Project: Law School Outcomes Agent
Case study: A law school applicant comparing schools. A governed data agent cleans simulated
school disclosure imports, scores their consistency, and publishes school-level employment
outcomes to a dashboard -- never auto-publishing a held import without a person's release.
Style: clean and professional, neutral colors, short captions readable in five seconds, no voiceover.

Use my attached screenshots. Do not invent any numbers; use only what is on the screenshots.

Six scenes, five seconds each:
1. 0-5 s: Title: Law School Outcomes Agent and one line on the case study.
2. 5-10 s: A new data file arrives every minute; show its file name being logged.
3. 10-15 s: Mixture of experts: records routed to Jev and Claude; use the Models (MoE) screenshot.
4. 15-20 s: The statistic decides: show the formula with its values and the threshold; the decision branch lights up.
5. 20-25 s: The action: the import is held, an alert appears, a person releases it, and the dashboard updates.
6. 25-30 s: Proof: live app link [FILL IN ONCE DEPLOYED], GitHub repo [FILL IN ONCE PUSHED], and the filled BINGO card.
```

Show the governance moment (the human release), not only the technology.
