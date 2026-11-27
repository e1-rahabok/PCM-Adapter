# Cluster Performance KPI

**Cluster Performance** is a 0 to 100 % score for a vSphere cluster. 100 is best. It measures the contention the VMs have now, from 9 sub-metrics. What it means and how to read it: Agent E2's [Cluster Performance (%)](https://github.com/e1-rahabok/agent-e2/blob/main/knowledge/vsphere/object-types/cluster/cluster-performance.md).

The KPI and its 9 sub-metrics are published on the cluster object under `vCommunity|Cluster Performance`. The KPI is `vCommunity|Cluster Performance|Cluster Performance Score`.

Code: [`Management Pack/app/metrics/cluster/cluster_performance_metrics.py`](../../../Management%20Pack/app/metrics/cluster/cluster_performance_metrics.py)

Source of the sub-metrics and limits: [`formula/cluster-performance.png`](formula/cluster-performance.png)

## Step 1: Collect the 9 sub-metrics

Eight sub-metrics take the worst VM and the 90th percentile of the powered-on VMs in the cluster. The ninth is the worst host's bad network packets. Every sub-metric is lower-is-better, and 0 is best.

VCF Operations shows the eight VM rows under a label in the words of the Agent E2 catalog: the CPU and disk rows read a 20-second peak, so their labels say peak, and the memory rows are [Memory Wait](memory-wait.md): Memory Contention plus NVMe wait, so their key keeps the word latency and their label says wait. The key stays the sub-metric name: a new key would be a new metric, without its history.

| Group | Sub-metric (key) | Label in VCF Operations | How it is calculated |
| :--- | :--- | :--- | :--- |
| Worst VM | Worst VM CPU Ready | Worst peak vCPU Ready among all VMs | Highest `cpu\|20_sec_peak_readyPct` of any VM |
| Worst VM | Worst VM CPU Co-Stop | Worst peak vCPU Co-stop among all VMs | Highest `cpu\|20_sec_peak_costopPct` of any VM |
| Worst VM | Worst VM Memory Latency | Worst peak memory wait among all VMs | Highest [Memory Wait](memory-wait.md) of any VM |
| Worst VM | Worst VM Disk Latency | Worst peak disk latency among all VM virtual disks | Highest `virtualDisk\|20_sec_peak_totalLatency_average` of any VM |
| 90th percentile | 90th Percentile VM CPU Ready | 90th percentile peak vCPU Ready among VMs | 90th percentile of `cpu\|20_sec_peak_readyPct` across the VMs |
| 90th percentile | 90th Percentile VM CPU Co-Stop | 90th percentile peak vCPU Co-stop among VMs | 90th percentile of `cpu\|20_sec_peak_costopPct` across the VMs |
| 90th percentile | 90th Percentile VM Memory Latency | 90th percentile peak memory wait among VMs | 90th percentile of [Memory Wait](memory-wait.md) across the VMs |
| 90th percentile | 90th Percentile VM Disk Latency | 90th percentile peak disk latency among VM virtual disks | 90th percentile of `virtualDisk\|20_sec_peak_totalLatency_average` across the VMs |
| ESXi | Highest ESXi Bad Network Packets | Highest ESXi (error + dropped) network packets | Per host: `(errorsRx + errorsTx + droppedRx + droppedTx) / (packetsRx + packetsTx) × 100` in the last collection cycle (5 minutes). The sub-metric is the highest host. |

Notes:

- **Which VMs count.** The powered-on VMs on the cluster's hosts. Powered-off VMs are left out because their last stats are old. Placement is read from VCF Operations properties: a host belongs to the cluster named in its `summary|parentCluster`, a VM runs on the host named in its `summary|parentHost`, and it is powered on when `summary|runtime|powerState` is "Powered On". Placement is by name, and names are unique only inside one datacenter, so two clusters with the same name in different datacenters of one vCenter can be mixed up.
- **Memory wait.** The memory rows are not the Memory Contention counter. They are the VM's Memory Wait: Memory Contention plus NVMe wait. See [Memory Wait](memory-wait.md).
- **20-second peaks.** The VM stats are 20-second peaks rather than 5-minute averages.
- **90th percentile.** The value that 90 % of the VMs are at or below. The VMs are sorted, and the one at position 90 % of the count, rounded up, is taken. With 20 VMs that is the 18th lowest. With fewer than 10 VMs it is the highest, the same as the worst VM.
- **Bad network packets** use the last collection cycle, as the "Bad Network Packets" super metric did. They are never averaged over a longer time. Two of the counters, Total Packets Received and Transmitted, are deactivated by default in VCF Operations. Activate them first: see [Policy](../../configuration-guide/policy.md).

## Step 2: Score each sub-metric

Each sub-metric is scored from its limits in [Thresholds](#thresholds), with the rule every KPI shares: the score falls in a straight line between the limits, from 100 to 0. The rule and its tiers are in [KPI scoring rules](../../concepts/kpi-scoring-models.md#five-limits-per-sub-metric).

## Step 3: Combine

The nine scores are combined as a weighted average. A sub-metric's weight grows as its score falls. The formula and the reasons for it are in [Combining the sub-metrics](../../concepts/kpi-scoring-models.md#combining-the-sub-metrics).

Because the weight grows smoothly as the score falls, a sub-metric that gets worse can raise the KPI. This happens while that sub-metric is still better than the sub-metrics that already pull the KPI down. [A worse sub-metric can lower Cluster Risk](cluster-risk.md#known-limitation-a-worse-sub-metric-can-lower-cluster-risk) explains it; Cluster Performance has the same effect in the other direction.

## Thresholds

| Sub-metric | Unit | Green ends at | Yellow ends at | Orange ends at | Score hits 0 at |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Worst VM CPU Ready | % | 4 | 8 | 16 | 32 |
| Worst VM CPU Co-Stop | % | 2 | 4 | 8 | 16 |
| Worst VM Memory Latency | % | 1 | 2 | 4 | 8 |
| Worst VM Disk Latency | ms | 40 | 80 | 160 | 320 |
| 90th Percentile VM CPU Ready | % | 1 | 2 | 4 | 8 |
| 90th Percentile VM CPU Co-Stop | % | 0.5 | 1 | 2 | 4 |
| 90th Percentile VM Memory Latency | % | 0.5 | 1 | 2 | 4 |
| 90th Percentile VM Disk Latency | ms | 20 | 40 | 60 | 80 |
| Highest ESXi Bad Network Packets | % | Excluded (exactly 0) | 0.2 | 0.4 | 0.8 |

Why the limits are what they are, and why the worst-VM rows have higher limits than the 90th-percentile rows: Agent E2's [Cluster Performance (%)](https://github.com/e1-rahabok/agent-e2/blob/main/knowledge/vsphere/object-types/cluster/cluster-performance.md) and [KPI design](https://github.com/e1-rahabok/agent-e2/blob/main/knowledge/sp5-framework/performance/performance-kpi-design.md), section Depth and breadth.

**Excluded.** The source table marks the green range of bad network packets, exactly 0, as "Excluded". While the value is 0, the sub-metric is left out of the KPI. Any bad packet is yellow, and then it counts.

## Worked examples

- **All 9 sub-metrics are 0.** Bad network packets are left out. The other 8 score 100 with weight 1. KPI = **100**.
- **The same, except 90th Percentile VM CPU Ready = 5** (red tier):
  - 5 is a quarter of the way through red (4 to 8), so it scores `25 − (¼ × 25) = 18.75`, with weight `2^(81.25 / 25)` ≈ 9.51.
  - Bad network packets are 0 and left out. The other 7 score 100 with weight 1.
  - KPI = `(7 × 100 + 18.75 × 9.51) / (7 + 9.51)` ≈ **53.19**.
  - A plain average would give about 89.8.
- **The same as the first, except a small share of bad packets (0.005 %).** It is yellow, scores about 74.4 with weight 2.03, and now counts. KPI ≈ **94.80**.
- **One VM of ten has 200 ms disk latency, the others 0.** Worst VM Disk Latency is 200, in red. The 90th percentile is the 9th lowest of the 10 VMs, so it stays 0. With fewer than 10 VMs, the 90th percentile is the worst VM, so it would also be 200.

The tests in [`Management Pack/tests/test_cluster_performance_metrics.py`](../../../Management%20Pack/tests/test_cluster_performance_metrics.py) check the same examples.

## Missing data

A sub-metric with no data is not published for that collection cycle, and it is left out of the KPI. It is never counted as 0, because 0 means best and would make the cluster look healthier than it is.

A stat whose latest value is more than 10 minutes old counts as no data. See [No stale values](README.md#no-stale-values).

- The adapter log lists, per cluster, the sub-metrics that were left out.
- If no sub-metric has data, the KPI is not published.

Common reasons for no data: the cluster has no powered-on VMs, the vCenter adapter has not yet collected the source stat, or the stats request to VCF Operations failed.

## Related KPIs

- [ESXi Performance](esxi-performance.md) uses the same 9 sub-metrics for the VMs on one host.
- [Cluster Risk](cluster-risk.md) is the leading indicator: how close the cluster is to contention. Memory ballooning and swapping are scored there.

## Changing the KPI

The code follows the source table: one section per row, in the same order, with the row's limits, the stats it reads and its formula. The 8 VM rows are shared with ESXi Performance and defined once, in [`Management Pack/app/metrics/vm/contention_by_vms.py`](../../../Management%20Pack/app/metrics/vm/contention_by_vms.py). A limit changed there changes in both KPIs.

The tiers and the weight formula are `TIERS` and `weight_for_score()` in [`Management Pack/app/metrics/kpi_score.py`](../../../Management%20Pack/app/metrics/kpi_score.py). That file scores every KPI, so a change there changes all of them.

- To change a limit, edit the row.
- To add a VM stat, add a section to `contention_by_vms.py` with the stat and its two rows (worst VM and 90th percentile), and add it to `VM_CONTENTION`. Both KPIs then get the two new rows.

The adapter definition reads the same table, so nothing else needs to change.
