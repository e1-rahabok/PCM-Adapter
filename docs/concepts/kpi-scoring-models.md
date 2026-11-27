# KPI Scoring Models

Each KPI of the VCF vCommunity Adapter (Performance, Consumption, Risk) is one 0 to 100 % number built from sub-metrics. Every sub-metric gets a color from its limits, and the adapter combines the colors as a **weighted average by color**, with the rules below.

Why a weighted average, and the other ways to combine the colors that were compared (a weighted sum, the worst color, weights by rank), are Agent E2's knowledge: [Modelling a pillar into one number](https://github.com/e1-rahabok/agent-e2/blob/main/knowledge/sp5-framework/concepts/modelling.md), section Three ways to combine the colours, and [KPI design](https://github.com/e1-rahabok/agent-e2/blob/main/knowledge/sp5-framework/performance/performance-kpi-design.md), section Scoring. Each KPI's own page lists its sub-metrics and their limits, for example [Cluster Performance](../reference/metrics/cluster-performance.md).

A known effect of the weighted average: when a KPI is already bad, a sub-metric that gets worse can move it the wrong way. See [A worse sub-metric can lower Cluster Risk](../reference/metrics/cluster-risk.md#known-limitation-a-worse-sub-metric-can-lower-cluster-risk).

## KPI scoring rules

Every KPI uses the calculation below. A KPI's own page lists its sub-metrics and their limits. The code is in [`kpi_score.py`](../../Management%20Pack/app/metrics/kpi_score.py).

### Five limits per sub-metric

Each sub-metric has five limits: the values where its score is 100, 75, 50, 25 and 0. They divide the values into four tiers. Within a tier, the score changes linearly:

| Tier | Value range | Score from → to |
| :--- | :--- | :--- |
| Green | best limit to green limit | 100 → 75 |
| Yellow | green limit to yellow limit | 75 → 50 |
| Orange | yellow limit to orange limit | 50 → 25 |
| Red | orange limit to zero-at limit | 25 → 0 |

Beyond the zero-at limit the score stays at 0. A value better than the best limit scores 100.

- **Lower is better** (for example CPU Ready): the limits increase.
- **Higher is better** (for example Guest Free Memory): the limits decrease. The same calculation handles both.
- **The best limit is not always 0.** For Worst ESXi CPU Imbalance it is 1, one running thread per running core, so every value up to 1 scores 100.

### Combining the sub-metrics

```
KPI = Σ(score × weight) / Σ(weight)
weight = 2^((100 − score) / 25)
```

The weight depends on the score, not on the tier. It is 1 at score 100, 2 at 75, 4 at 50, 8 at 25 and 16 at 0, and changes smoothly in between, so the KPI does not jump when a value crosses a limit.

![How much each sub-metric counts, by its score](images/kpi-weights.svg)

With a plain average, one sub-metric in the red tier is hidden by nine healthy ones. With the weights it stays visible. For example, with 10 sub-metrics, nine at 100 and one at 18.75 (red):

- Plain average: about 91.9. The problem is hidden.
- Weighted: `(9 × 100 + 18.75 × 9.51) / (9 + 9.51)` ≈ 58.25. The problem shows.

### Rounding

Each value is rounded to two decimals before it is scored, and the KPI is calculated from the rounded values. This way the KPI matches the sub-metric values that users see.

### Green as a single value

Some source tables give green as one value, such as "0 %", rather than a range. In that case the green limit equals the best limit. Only exactly 0 is green and scores 100. Any other value starts in yellow, at 75 with weight 2. Because values are rounded first, noise below 0.005 still counts as 0.

### Skip when green

Some source tables mark a green range as "Excluded". While such a value is green, the sub-metric is left out of the KPI, as if it had no data. Once it leaves green, it counts like any other sub-metric. Why these sub-metrics are skipped: [Modelling a pillar into one number](https://github.com/e1-rahabok/agent-e2/blob/main/knowledge/sp5-framework/concepts/modelling.md), section Rare and rarely-green metrics.

- Green means the value is at the best limit or better, or has not reached the green limit. The check uses the value, not the weight, because the weight changes smoothly.
- If every sub-metric with data is skipped this way, the KPI is 100.

Which sub-metrics are skipped when green is listed in the "Excluded" section of each KPI: [Cluster Performance](../reference/metrics/cluster-performance.md), [VM Performance](../reference/metrics/vm-performance.md), [Cluster Risk](../reference/metrics/cluster-risk.md) and [ESXi Performance](../reference/metrics/esxi-performance.md).

### Missing data

A sub-metric with no data is left out of the KPI. It is never counted as 0, because for most sub-metrics 0 means "perfect" and would make the object look healthier than it is.

- If no sub-metric has data, the KPI is not published for that cycle. If some had data but all were skipped when green, the KPI is 100.
- In the code, a sub-metric with no data returns `None`, never 0.

How the code is organised is described in [Metrics Code](../development-guide/metrics-code.md).

## Related

- [Capacity Management Model](capacity-management.md): how Consumption, Contention and Risk decide whether a cluster can take more VMs.
- [Cluster Risk](../reference/metrics/cluster-risk.md), [Cluster Consumption](../reference/metrics/cluster-consumption.md), [Cluster Performance](../reference/metrics/cluster-performance.md): the KPIs and their sub-metrics.
