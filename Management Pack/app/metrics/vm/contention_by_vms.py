#  Copyright 2026 VCF Operations vCommunity Management Pack
"""VM contention of a group of VMs, the rows shared by Cluster Performance and ESXi Performance.

For each of 4 VM stats, two rows: how deep (the worst VM) and how broad (the 90th percentile of the VMs).
Both KPIs use these rows, so a limit changed here changes in both. The rows carry the name of their scope, "among all
VMs" for a cluster and "among VMs on the host" for a host, so that a name says what it measures.

The memory row is Memory Wait, not the Memory Contention counter: see metrics/vm/memory_wait.py.
"""
import logging
from typing import Dict, List, NamedTuple, Optional
from aria.ops.suite_api_client import SuiteApiClient
from metrics.kpi_score import Metric, percentile_90
from metrics.vm import memory_wait
from metrics.vm.memory_wait import VmMemoryContext
from utils.ops_stats import read_latest_stats

logger = logging.getLogger(__name__)


# =================================================================================================================
# Part 1. How deep and how broad
# =================================================================================================================

class VmContentionRows(NamedTuple):
    """One VM stat and the two rows it gives: the worst VM (how deep) and the 90th percentile (how broad)."""
    stat: str
    worst: Metric
    percentile_90: Metric


class Scope(NamedTuple):
    """The words that say which VMs a row covers."""
    vms_worst: str              # "among all VMs"
    vms_percentile: str         # "among VMs"
    disks_worst: str            # "among all VM virtual disks"
    disks_percentile: str       # "among VM virtual disks"


CLUSTER_SCOPE = Scope("among all VMs", "among VMs", "among all VM virtual disks", "among VM virtual disks")
HOST_SCOPE = Scope(
    "among VMs on the host", "among VMs on the host",
    "among virtual disks of VMs on the host", "among virtual disks of VMs on the host",
)

# The synthetic stat of the memory row: Memory Wait, worked out for each VM by with_memory_wait().
MEMORY_WAIT_STAT = "memory wait"


# =================================================================================================================
# Part 2. The 4 VM contention stats
# =================================================================================================================
#
# Every row is "lower is better", and 0 is perfect. The five numbers of each Metric are the values where its score is
# 100, 75, 50, 25 and 0. The worst-VM limits are higher than the 90th-percentile limits, because a single VM peaks
# far above most of the others. The CPU and disk stats are the 20-second peaks, not the 5-minute averages, so the KPIs
# are leading indicators: "peak" is in their names. Memory Wait is a 20-second peak of Memory Contention plus the NVMe
# wait of the latest values, so it has no "peak" in its name.
#       name                                 unit   best  green  yellow  orange  zero-at

def vm_contention_rows(scope: Scope) -> List[VmContentionRows]:
    """The 4 stats and their 8 rows, named for a scope: a cluster or a host."""
    return [
        # --- CPU Ready: time the VM was ready to run, but had to wait for a physical CPU --------------------------
        VmContentionRows(
            "cpu|20_sec_peak_readyPct",
            Metric(f"Worst peak vCPU Ready {scope.vms_worst}",                   "%",   0.0,  4.0,   8.0,    16.0,   32.0),
            Metric(f"90th percentile peak vCPU Ready {scope.vms_percentile}",    "%",   0.0,  1.0,   2.0,    4.0,    8.0),
        ),
        # --- CPU Co-Stop: time a multi-vCPU VM was held back, so that its vCPUs stay in step ----------------------
        VmContentionRows(
            "cpu|20_sec_peak_costopPct",
            Metric(f"Worst peak vCPU Co-stop {scope.vms_worst}",                 "%",   0.0,  2.0,   4.0,    8.0,    16.0),
            Metric(f"90th percentile peak vCPU Co-stop {scope.vms_percentile}",  "%",   0.0,  0.5,   1.0,    2.0,    4.0),
        ),
        # --- Memory Wait: Memory Contention plus NVMe wait, see metrics/vm/memory_wait.py --------------------------
        VmContentionRows(
            MEMORY_WAIT_STAT,
            Metric(f"Worst memory wait {scope.vms_worst}",                       "%",   0.0,  1.0,   2.0,    4.0,    8.0),
            Metric(f"90th percentile memory wait {scope.vms_percentile}",        "%",   0.0,  0.5,   1.0,    2.0,    4.0),
        ),
        # --- Disk Latency: read and write latency of the VM's virtual disks ---------------------------------------
        VmContentionRows(
            "virtualDisk|20_sec_peak_totalLatency_average",
            Metric(f"Worst peak disk latency {scope.disks_worst}",               "ms",  0.0,  40.0,  80.0,   160.0,  320.0),
            Metric(f"90th percentile peak disk latency {scope.disks_percentile}", "ms", 0.0,  20.0,  40.0,   60.0,   80.0),
        ),
    ]


CLUSTER_ROWS = vm_contention_rows(CLUSTER_SCOPE)
HOST_ROWS = vm_contention_rows(HOST_SCOPE)


def contention_metrics(rows: List[VmContentionRows]) -> List[Metric]:
    """The 8 rows, in the order of the source tables: the 4 worst-VM rows, then the 4 90th-percentile rows."""
    return [r.worst for r in rows] + [r.percentile_90 for r in rows]


CLUSTER_METRICS = contention_metrics(CLUSTER_ROWS)
HOST_METRICS = contention_metrics(HOST_ROWS)

# The VM stats asked from VCF Operations for each VM, as VCF Operations names them: the memory row reads Memory
# Contention and the NVMe read bandwidth, and works Memory Wait out from them.
VM_STATS = [r.stat for r in CLUSTER_ROWS if r.stat != MEMORY_WAIT_STAT] + memory_wait.VM_STATS


def with_memory_wait(
    stats_by_vm: Dict[str, Dict[str, float]], vm_ids: List[str], vm_context: Dict[str, VmMemoryContext],
    host_latency_us: Dict[str, float],
) -> Dict[str, Dict[str, float]]:
    """stats_by_vm, with the Memory Wait of each VM in vm_ids added. A VM with no Memory Contention gets none.

    vm_context is {VM id: its vCPUs and host}, host_latency_us {host id: NVMe read latency in microseconds}. Both
    may be empty: Memory Wait is then the Memory Contention alone.
    """
    result = dict(stats_by_vm)
    for vm_id in vm_ids:
        vm_stats = stats_by_vm.get(vm_id, {})
        context = vm_context.get(vm_id)
        wait = memory_wait.memory_wait_pct(
            vm_stats,
            context.vcpus if context else None,
            host_latency_us.get(context.host_id) if context else None,
        )
        if wait is not None:
            result[vm_id] = {**vm_stats, MEMORY_WAIT_STAT: wait}
    return result


def worst_and_percentile(
    rows: List[VmContentionRows], stats_by_vm: Dict[str, Dict[str, float]], vm_ids: List[str]
) -> Dict[str, Optional[float]]:
    """The value of the 8 VM contention rows, over the VMs in vm_ids. None means "no data".

    stats_by_vm must already hold the Memory Wait of each VM, see with_memory_wait().
    """
    values = {}
    for row in rows:
        # A VM that does not have this stat is left out.
        per_vm = [stats_by_vm[vm_id][row.stat] for vm_id in vm_ids if row.stat in stats_by_vm.get(vm_id, {})]
        values[row.worst.name] = max(per_vm) if per_vm else None
        values[row.percentile_90.name] = percentile_90(per_vm)
    return values


# =================================================================================================================
# Part 3. Reading the stats. One request for many VMs, never one per VM.
# =================================================================================================================

def read_vm_contention_stats(suite_api_client: SuiteApiClient, vm_ids: List[str]) -> Dict[str, Dict[str, float]]:
    """{VM resource id: {stat key: latest value}} for the stats in VM_STATS."""
    return read_latest_stats(suite_api_client, vm_ids, VM_STATS)


def read_host_nvme_latency(suite_api_client: SuiteApiClient, host_ids: List[str]) -> Dict[str, float]:
    """{host resource id: NVMe read latency in microseconds}. Only hosts with memory tiering have it.

    A failed read gives {}: Memory Wait is then the Memory Contention alone, and the log says so.
    """
    if not host_ids:
        return {}
    try:
        stats = read_latest_stats(suite_api_client, host_ids, memory_wait.HOST_STATS)
    except Exception as e:
        logger.warning(f"Failed to read the NVMe read latency of the hosts, so Memory Wait has no NVMe wait - {repr(e)}")
        return {}
    return {
        host_id: values[memory_wait.NVME_READ_LATENCY]
        for host_id, values in stats.items() if memory_wait.NVME_READ_LATENCY in values
    }
