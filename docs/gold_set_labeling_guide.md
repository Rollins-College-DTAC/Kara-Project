# Gold set labeling guide

The gold set is 50 notes labeled by hand **before any model sees them**. It is the answer key used to score the experts. Label from the note alone, the way a careful paralegal would, not from what a model might say.

Open `gold_set.csv` in Excel or Numbers, fill in the columns below, save as CSV, and keep the column names unchanged. Put your initials in `labeled_by`, and use `label_notes` for anything you were unsure about.

## Classification columns (every row)

**category**: pick one of these:

- `scholarship_terms`: conditions to keep a scholarship, the renewal GPA, or how many recipients kept their awards
- `funded_or_clerkship`: counts of school-funded positions, fellowships or clerkships
- `employment_narrative`: where graduates found jobs or which sector placed best, without counts or salaries
- `salary`: salary figures for this school's graduates
- `bar_passage`: bar results, or which takers and jurisdictions they cover
- `other`: none of the above, contact details, or nothing substantive

Empty notes are `other`. If a note covers two topics, pick the one that matters more to an applicant and say so in `label_notes`.

**urgency**: pick one of `low`, `medium`, `high` or `critical`, meaning how much an applicant comparing schools needs to see the note. Empty notes are `low`.

**injection**: `true` if the note tries to instruct a computer or AI (rank, skip checks, publish, mark verified), otherwise `false`.

## Extraction columns (leave blank unless the note states the value)

| Column | What to enter |
|---|---|
| `retention_gpa` | the GPA needed to keep a scholarship, for example `3.0` |
| `retention_pct` | percent of recipients who kept their awards, from 0 to 100 ("ninety percent" is `90`) |
| `school_funded_count` | a whole number, only if a number is given |
| `clerkship_count` | a whole number, only if a number is given ("a handful" stays blank) |
| `median_salary_usd` | full dollars ("$95K" is `95000`) |
| `top_sector` | `small_firm`, `large_firm`, `government`, `public_interest`, `business_industry` or `clerkship`, only if the note names the strongest sector |

**Blank means "not stated".** Leave a field blank when:

- the figure belongs to another school, or the note says it is not reported
- the note is vague
- the record is an injection

Scoring counts any value a model fills in where your label is blank as an **invented** value, and the pass bar allows none. So be strict.

## When you are done

1. Save the file and tell Claude. Nobody changes the labels after scoring starts, and nobody moves the pass bar in `config.toml`.
2. Run `uv run python scripts/evaluate.py --offline` first. This uses rules only and is free.
3. Then run `uv run python scripts/evaluate.py` with your key in `.env`.
