# Open questions

Questions about PCM-Adapter only, for the author (WD-019 in the workspace's [DECISIONS.md](https://github.com/e1-rahabok/private-cloud-workspace/blob/main/DECISIONS.md)). A question that binds several repositories goes to the workspace's [OPEN-QUESTIONS.md](https://github.com/e1-rahabok/private-cloud-workspace/blob/main/OPEN-QUESTIONS.md). IDs are `Q-ADP-n` (WD-038). Write the reply after `Answer:`.

No question is open.

## Answered

### Q-ADP-1 The style baseline of the documentation

The workspace's style check (R-WS-006, [tools/style.py](https://github.com/e1-rahabok/private-cloud-workspace/blob/main/tools/style.py)) found 770 problems in 57 documents on its first run: 693 are tables too wide or too wordy for GitHub, 77 are long or sentence headings. 343 sit in one file, [metrics-and-properties.md](docs/reference/metrics-and-properties.md), a reference table of every key with five columns of text. They are listed, file by file with their counts, in [style-baseline.yaml](style-baseline.yaml), which may only shrink: the pull request that fixes a file lowers its count.

- (a) Keep the baseline. A file is fixed when it is next edited.
- (b) Fix them all in M2, the milestone open now in the workspace's [ROADMAP.md](https://github.com/e1-rahabok/private-cloud-workspace/blob/main/ROADMAP.md); metrics-and-properties.md becomes one block per key or one table per object type with fewer columns.

- **Recommendation:** (a). metrics-and-properties.md is split into one table per object type, with at most four columns, in the next pull request that changes its keys, so the split is checked against the code in the same review.

Answer: "agree" (2026-11-28).

- Follows: the baseline stays, and each file's count drops when it is next fixed. The split of metrics-and-properties.md is a rule in [CLAUDE-PROJECT.md](CLAUDE-PROJECT.md), section Documentation.
