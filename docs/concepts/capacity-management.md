# Capacity Management Model

The capacity model decides whether a vSphere cluster can take more VMs. The VCF vCommunity Adapter computes the running stage of the model for every cluster from live data, and publishes the decision as **Close for Business**.

The model itself is Agent E2's knowledge: its planning and running stages, its measures and how they relate are in [Capacity management](https://github.com/e1-rahabok/agent-e2/blob/main/knowledge/sp5-framework/capacity/README.md), [Capacity demand](https://github.com/e1-rahabok/agent-e2/blob/main/knowledge/sp5-framework/capacity/demand.md), [Supply: total and usable capacity](https://github.com/e1-rahabok/agent-e2/blob/main/knowledge/sp5-framework/capacity/supply.md) and [Can this cluster take more VMs?](https://github.com/e1-rahabok/agent-e2/blob/main/knowledge/vsphere/object-types/cluster/decision-tree/can-cluster-take-more-vms.md). This page lists what the adapter publishes for it.

## What the adapter publishes

| Measure of the model | Published on each cluster | Calculation |
| :--- | :--- | :--- |
| Consumption | `vCommunity\|Cluster Consumption\|Cluster Consumption Score` | [Cluster Consumption](../reference/metrics/cluster-consumption.md) |
| Contention | `vCommunity\|Cluster Performance\|Cluster Performance Score` | [Cluster Performance](../reference/metrics/cluster-performance.md) |
| Risk | `vCommunity\|Cluster Risk\|Cluster Risk Score` | [Cluster Risk](../reference/metrics/cluster-risk.md) |
| The decision | `vCommunity\|Periodic Cluster Check\|Close for Business`, once per period | [Periodic Cluster Check](../reference/metrics/periodic-cluster-check.md) |

- **Share** is published on each VM, as `vCommunity|Configuration|Share per vCPU` and `Share per MB of Memory`. See [VM Shares](../reference/metrics/vm-shares.md).
- **Buffer** is not published. VCF Operations takes HA and the Capacity Buffer (Demand) of its policy out of the usable capacity that Cluster Consumption divides by. See [Usable Capacity](../reference/metrics/cluster-consumption.md#usable-capacity).
- **The planning stage** is not computed: the adapter reads no planned utilization, allocation or reservation per class of service.

## Closing the cluster

The adapter computes the overcommit path of the model's closure logic, in the [Periodic Cluster Check](../reference/metrics/periodic-cluster-check.md). The path without overcommit, allocation against usable capacity, is not computed.

- The three scores use the same 0-100 % scale and the same four bands. Cluster Performance is higher-is-better. Cluster Risk and Cluster Consumption are higher-is-worse.
- **Close for Business** is 1 when Consumption or Performance is at its red closure level, or when both are at their orange closure level and Risk is orange or red. Risk alone never closes a cluster.
- The closure levels sit inside the bands: red above 80 and orange above 60 for Consumption and Risk, and red below 20 and orange below 40 for Performance. A Consumption of 78 shows red and leaves the cluster open. See [The rule](../reference/metrics/periodic-cluster-check.md#the-rule).
- Every cluster closes at Risk orange, the model's setting for production clusters. The model's setting for non-production clusters, Risk red, is not computed.
- Cluster Consumption is measured against usable capacity: Total − HA − Buffer, as VCF Operations calculates it from the cluster's HA admission control and the Capacity Buffer (Demand) in its policy.
- Cluster Risk is measured against each host's physical capacity. Besides the four leading indicators of the model (monster VM, imbalance, overcommit ratio and reservation), it scores the busiest host's utilization and memory saturation.
- Each score is summarized by the worst end of the period. See [Worst](../reference/metrics/periodic-cluster-check.md#worst).
- The decision is published as a metric on the cluster once per period, for dashboards, reports, alerts and placement automation. See the [vSphere Cluster Capacity 2.0 Dashboard](../user-guide/vsphere-cluster-capacity-dashboard.md).
