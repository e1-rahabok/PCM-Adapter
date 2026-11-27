# Requirements: clean-up of PCM-Adapter

The clean-up of PCM-Adapter in milestone M2 of the workspace's [ROADMAP.md](https://github.com/e1-rahabok/private-cloud-workspace/blob/main/ROADMAP.md), R-REPO-009 in M7: knowledge pages that belong to Agent E2. Question IDs point at the interview ([round 1](https://github.com/e1-rahabok/private-cloud-workspace/blob/main/spec/interview-round-1.md), [round 2](https://github.com/e1-rahabok/private-cloud-workspace/blob/main/spec/interview-round-2.md), [round 3](https://github.com/e1-rahabok/private-cloud-workspace/blob/main/spec/interview-round-3.md), [round 4](https://github.com/e1-rahabok/private-cloud-workspace/blob/main/spec/interview-round-4.md)); other IDs are explained in the [glossary](https://github.com/e1-rahabok/private-cloud-workspace/blob/main/spec/glossary.md).

## Knowledge in the right place

### R-REPO-001 Every fact in the VCF vCommunity Adapter's knowledge pages exists in Agent E2 first

Milestone: M2.

Source: WD-025 (the adapter's documentation points to the knowledge instead of repeating it); WD-001 (Agent E2 owns domain knowledge).

- Given VCF vCommunity Adapter's knowledge pages: [docs/concepts/capacity-management.md](https://github.com/e1-rahabok/PCM-Adapter/blob/main/docs/concepts/capacity-management.md), [docs/concepts/kpi-scoring-models.md](https://github.com/e1-rahabok/PCM-Adapter/blob/main/docs/concepts/kpi-scoring-models.md), and the explanatory sections of the pages in [docs/reference/metrics](https://github.com/e1-rahabok/PCM-Adapter/tree/main/docs/reference/metrics)
- When their facts are compared with Agent E2's knowledge base
- Then every fact is found in a knowledge file, or is quoted word for word in a Q-E2 question in agent-e2's [author-questions.md](https://github.com/e1-rahabok/agent-e2/blob/main/project/author-questions.md), with the adapter page and the commit it came from, so the author chooses what enters the knowledge (agent-e2 adds source documents only from the author)
- And a fact that contradicts the knowledge base is quoted the same way, beside the knowledge file it contradicts, for the author to settle
- And only then is the page trimmed by R-REPO-002; git keeps the page, and the question keeps each fact that was not in the knowledge base, so none is dropped

Test scenarios:
- T-REPO-001a (anywhere, manual with an AI comparison): extract the claims of each adapter page; for each, name the knowledge file and line that holds it, or the Q-E2 question that quotes it. Expect a complete table with no claim unaccounted for, kept in the pull request that removes the pages.

### R-REPO-002 VCF vCommunity Adapter's documentation keeps only what the adapter does

Milestone: M2.

Source: WD-025; the author's message of 2026-11-26 naming the adapter's concept and metric pages as knowledge that belongs to Agent E2.

- Given VCF vCommunity Adapter's documentation after R-REPO-001
- When a reader opens a metric or concept page
- Then it describes what the adapter computes and publishes (keys, inputs, settings, states) and how to install and run it
- And for what a metric means and how to use it, it links to the Agent E2 knowledge file
- And the README presents the adapter as one part of Private Cloud Manager, with links to Agent E2 and PCM, and names the simplest deployment: the pak file alone

Test scenarios:
- T-REPO-002a (anywhere, manual review by a fresh session): read every page of the adapter's docs; expect no explanation of a metric's meaning beyond one sentence, and a knowledge link on each metric page.
- T-REPO-002b (anywhere, automated by the adapter's existing link check, [check_links.py](https://github.com/e1-rahabok/PCM-Adapter/blob/main/tools/check-docs/check_links.py)): expect no broken link after the pages are removed.

### R-REPO-009 The adapter's documentation links to isvara.io's articles

Milestone: M7.

Source: WD-025 (the adapter's documentation points to the knowledge); [WD-017](https://github.com/e1-rahabok/private-cloud-workspace/blob/main/DECISIONS.md) (isvara.io's articles from Agent E2's knowledge files).

- Given the adapter's metric and concept pages after R-REPO-002, which link to Agent E2's knowledge files
- When isvara.io's rebuilt site is switched over in M7
- Then each link to a knowledge file becomes a link to the article written from it

Test scenarios:
- T-REPO-009a (anywhere, automated by the adapter's link check, [check_links.py](https://github.com/e1-rahabok/PCM-Adapter/blob/main/tools/check-docs/check_links.py), extended): no page links to a file under agent-e2's `knowledge/`; every link to isvara.io names an article.
