#  Copyright 2026 VCF Operations vCommunity Management Pack
"""ESXi Performance KPI: one 0-100 % score per ESXi host, 100 is perfect.

It measures actual contention of the host's VMs, not potential: are the VMs on this host getting the CPU, memory,
disk and network they ask for? It is Cluster Performance, measured for one host.

Published on the host as vCommunity|ESXi Performance|ESXi Performance Score (the KPI) and its 9 rows.
A row with no data is left out of the KPI, never treated as 0.

Called from: collectors/host/collectHostData.py.
Limits: docs/reference/metrics/formula/esxi-performance.png. Description: docs/reference/metrics/esxi-performance.md
"""
import logging
from typing import Dict, List, Optional
from aria.ops.object import Object
from aria.ops.suite_api_client import SuiteApiClient
from metrics.kpi_score import publish_kpi
from metrics.host.host_bad_network_packets import bad_network_packets_metric, bad_packet_pct, read_host_packet_stats
from metrics.vm.contention_by_vms import (
    VM_CONTENTION, VM_CONTENTION_METRICS, worst_and_percentile, read_vm_contention_stats, read_host_nvme_latency, with_memory_wait,
)
from metrics.vm.memory_wait import VmMemoryContext

logger = logging.getLogger(__name__)

# The names shown in VCF Operations: the group that holds the metrics, and the KPI inside it.
GROUP = "ESXi Performance"
KPI_NAME = "ESXi Performance"
# The key of the KPI metric. It must differ from GROUP: VCF Operations rejects a metric key that equals
# the key of its group. The metric is still shown as KPI_NAME.
KPI_KEY = "ESXi Performance Score"


# =================================================================================================================
# Part 1. The 9 rows
# =================================================================================================================

# --- Rows 1-8. VM contention: how deep (the worst VM) and how broad (the 90th percentile) -----------------------
# Defined in metrics/vm/contention_by_vms.py, shared with Cluster Performance.

# --- Row 9. Bad network packets of the host itself -------------------------------------------------------------
BAD_PACKETS = bad_network_packets_metric("ESXi Bad Network Packets")

# The rows, in the order of the source table. Every row is published on the host: none exists there already.
METRICS = VM_CONTENTION_METRICS + [BAD_PACKETS]
PUBLISHED_METRICS = METRICS

# The labels VCF Operations shows, in the words of the Agent E2 catalog (knowledge/catalog/thresholds-performance.yaml).
# The keys stay the row names: renaming a key would start a new metric and leave its history behind. The CPU and disk
# rows read a 20-second peak, so their labels say peak. The memory rows are Memory Wait (Memory Contention plus NVMe wait,
# metrics/vm/memory_wait.py): the key keeps the word latency, the label says wait.
LABELS = dict(zip([metric.name for metric in VM_CONTENTION_METRICS], [
    "Worst peak vCPU Ready among VMs on the host",
    "Worst peak vCPU Co-stop among VMs on the host",
    "Worst memory wait among VMs on the host",
    "Worst peak disk latency among virtual disks of VMs on the host",
    "90th percentile peak vCPU Ready among VMs on the host",
    "90th percentile peak vCPU Co-stop among VMs on the host",
    "90th percentile memory wait among VMs on the host",
    "90th percentile peak disk latency among virtual disks of VMs on the host",
], strict=True))


# =================================================================================================================
# Part 2. Reading the stats, once for all hosts
# =================================================================================================================

class EsxiPerformanceStats:
    """The stats of one collection cycle: of every powered-on VM, the packet counters and the NVMe read latency of
    every host."""

    def __init__(self, vm_stats: Dict[str, Dict[str, float]], host_packet_stats: Dict[str, Dict[str, float]],
                 host_nvme_latency: Optional[Dict[str, float]] = None):
        self.vm_stats = vm_stats
        self.host_packet_stats = host_packet_stats
        self.host_nvme_latency = host_nvme_latency or {}


def read_esxi_performance_stats(
    suite_api_client: SuiteApiClient, vm_ids: List[str], host_ids: List[str]
) -> EsxiPerformanceStats:
    """Reads the stats of all VMs and all hosts in bulk, instead of one call per host."""
    try:
        return EsxiPerformanceStats(
            read_vm_contention_stats(suite_api_client, vm_ids),
            read_host_packet_stats(suite_api_client, host_ids),
            read_host_nvme_latency(suite_api_client, host_ids),
        )
    except Exception as e:
        # Without stats there is no score, but the rest of the host collection must still run.
        logger.warning(f"Failed to read ESXi Performance stats, so no ESXi Performance this cycle - {repr(e)}")
        return EsxiPerformanceStats({}, {})


# =================================================================================================================
# Part 3. The KPI, once per host
# =================================================================================================================

def esxi_performance_values(
    stats: EsxiPerformanceStats, host_id: str, vm_ids: List[str],
    vm_context: Optional[Dict[str, VmMemoryContext]] = None,
) -> Dict[str, Optional[float]]:
    """The value of every row for one host. None means "no data".

    The memory rows are Memory Wait: Memory Contention plus NVMe wait, see metrics/vm/memory_wait.py. vm_context
    gives each VM's vCPUs and host. Without it, Memory Wait is the Memory Contention alone.
    """
    vm_stats = with_memory_wait(stats.vm_stats, vm_ids, vm_context or {}, stats.host_nvme_latency)
    values = worst_and_percentile(VM_CONTENTION, vm_stats, vm_ids)
    values[BAD_PACKETS.name] = bad_packet_pct(stats.host_packet_stats.get(host_id, {}))
    return values


def collect_esxi_performance_metrics(
    host_obj: Object, host_name: str, host_id: str, vm_ids: List[str], stats: EsxiPerformanceStats,
    vm_context: Optional[Dict[str, VmMemoryContext]] = None,
) -> None:
    """Publishes the rows, then the ESXi Performance KPI computed from them.

    host_id is the VCF Operations id of this host, vm_ids those of the powered-on VMs on it.
    stats is the result of read_esxi_performance_stats(), vm_context the vCPUs and host of each VM.
    """
    try:
        values = esxi_performance_values(stats, host_id, vm_ids, vm_context)

        no_data = publish_kpi(host_obj, GROUP, KPI_KEY, METRICS, PUBLISHED_METRICS, values).no_data
        if no_data:
            logger.debug(f"ESXi Performance for {host_name}: no data, so left out: {', '.join(no_data)}")

    except Exception as e:
        # A failure here must not stop the collection of the other host data.
        logger.warning(f"Failed to retrieve ESXi Performance metrics for : {host_name} - {repr(e)}")
