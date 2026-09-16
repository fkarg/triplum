# Readable terminal reports

Snapshot 2026-09-16.

Render benchmark summaries as one compact block per run, with the full run id followed by
wrapped field/value pairs at the detected terminal width (80 columns when unavailable).
Show all fields and runs, omit dataframe shape/types/borders, display missing values as `n/a`,
and format floats to six significant digits. Long identifiers wrap without truncation.
The underlying summary DataFrame and metric calculations remain unchanged.

Apply the renderer to report and the summaries printed by run, sweep and rerun. The per-question
diff table remains separate. Empty summaries say `No benchmark runs recorded.`

Tests exercise 40/80/120-column output, long identifiers, missing values, zero values, more than
100 runs, and the report CLI using the actual run store.
