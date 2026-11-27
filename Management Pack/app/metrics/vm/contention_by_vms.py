#  Copyright 2026 VCF Operations vCommunity Management Pack
"""VM contention of a group of VMs, the rows shared by Cluster Performance and ESXi Performance.

For each of 4 VM stats, two rows: how deep (the worst VM) and how broad (the 90th percentile of the VMs).
Both KPIs use these rows, so a limit changed here changes in both. The name of a row is its metric key and never
changes (a new key is a new metric, without history); each KPI module gives the rows the label VCF Operations shows.

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


# The synthetic stat of the memory row: Memory Wait, worked out for each VM by with_memory_wait().
MEMORY_WAIT_STAT = "memory wait"


# =================================================================================================================
# Part 2. The 4 VM contention stats
# =================================================================================================================
#
# Every row is "lower is better", and 0 is perfect. The five numbers of each Metric are the values where its score is
# 100, 75, 50, 25 and 0. The worst-VM limits are higher than the 90th-percentile limits, because a single VM peaks
# far above most of the others. The CPU and disk stats are the 20-second peaks, not the 5-minute averages, so the KPIs
# are leading indicators: "peak" is in their labels. Memory Wait is a 20-second peak of Memory Contention plus the NVMe
# wait of the latest values; its catalog interval is 20s, so its label says peak too.
#       name                                 unit   best  green  yellow  orange  zero-at

VM_CONTENTION = [
    # --- CPU Ready: time the VM was ready to run, but had to wait for a physical CPU ------------------------------
    VmContentionRows(
        "cpu|20_sec_peak_readyPct",
        Metric("Worst VM CPU Ready",                "%",   0.0,  4.0,   8.0,    16.0,   32.0, interval="20s"),
        Metric("90th Percentile VM CPU Ready",      "%",   0.0,  1.0,   2.0,    4.0,    8.0, interval="20s"),
    ),
    # --- CPU Co-Stop: time a multi-vCPU VM was held back, so that its vCPUs stay in step --------------------------
    VmContentionRows(
        "cpu|20_sec_peak_costopPct",
        Metric("Worst VM CPU Co-Stop",              "%",   0.0,  2.0,   4.0,    8.0,    16.0, interval="20s"),
        Metric("90th Percentile VM CPU Co-Stop",    "%",   0.0,  0.5,   1.0,    2.0,    4.0, interval="20s"),
    ),
    # --- Memory Wait: Memory Contention plus NVMe wait, see metrics/vm/memory_wait.py. The key keeps the word
    # "Memory Latency" (it was the key before NVMe wait was scored); the label says Memory Wait. ----------------------
    VmContentionRows(
        MEMORY_WAIT_STAT,
        Metric("Worst VM Memory Latency",           "%",   0.0,  1.0,   2.0,    4.0,    8.0, interval="20s"),
        Metric("90th Percentile VM Memory Latency", "%",   0.0,  0.5,   1.0,    2.0,    4.0, interval="20s"),
    ),
    # --- Disk Latency: read and write latency of the VM's virtual disks -------------------------------------------
    VmContentionRows(
        "virtualDisk|20_sec_peak_totalLatency_average",
        Metric("Worst VM Disk Latency",             "ms",  0.0,  40.0,  80.0,   160.0,  320.0, interval="20s"),
        Metric("90th Percentile VM Disk Latency",   "ms",  0.0,  20.0,  40.0,   60.0,   80.0, interval="20s"),
    ),
]
# The 8 rows, in the order of the source tables: the 4 worst-VM rows, then the 4 90th-percentile rows.
VM_CONTENTION_METRICS = [rows.worst for rows in VM_CONTENTION] + [rows.percentile_90 for rows in VM_CONTENTION]

# The VM stats asked from VCF Operations for each VM, as VCF Operations names them: the memory row reads Memory
# Contention and the NVMe read bandwidth, and works Memory Wait out from them.
VM_STATS = [r.stat for r in VM_CONTENTION if r.stat != MEMORY_WAIT_STAT] + memory_wait.VM_STATS


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
