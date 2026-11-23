#  Copyright 2026 VCF Operations vCommunity Management Pack
"""Memory Wait of a VM: memory contention plus NVMe wait, in % of the VM's vCPU time.

Why this metric exists. With memory tiering, a VM's cold pages live on the NVMe tier. When a vCPU touches one, it
waits for the whole NVMe read. The vSphere Memory Contention counter does not count that wait (it is unaware of memory
tiering), so a VM that waits on NVMe can show a Memory Contention near 0. Memory Wait adds the missing part:

    Memory Wait = Memory Contention + NVMe wait

NVMe wait is computed, because no counter gives it (Little's law: fetches in flight = rate x time each takes):

    NVMe wait (%) = VM NVMe read bandwidth (MB/s) x 256 pages per MB x NVMe read latency of its host (s) / vCPUs x 100

A host without memory tiering has no NVMe stats, so its NVMe wait is 0 and Memory Wait is the Memory Contention.
When the VM has NVMe reads but its host latency or its vCPU count is unknown, Memory Wait is the Memory Contention
alone and understates the wait: the same happens when the stats are not collected (NVMe read latency is statistics
level 3, read bandwidth level 2).

Used by: VM Performance (one VM), Cluster Performance and ESXi Performance (the worst VM and the 90th percentile).
Description: docs/reference/metrics/memory-wait.md
"""
from typing import Dict, NamedTuple, Optional

# VM stat: Memory Contention, the 20-second peak.
MEMORY_CONTENTION = "mem|20_sec_peak_host_contentionPct"
# VM stat: read bandwidth of the NVMe memory tier, in MB/s. Not checked on a live VCF Operations yet: the key follows
# the host stats of the tier (mem:NVMe|latency.read_latest, mem:NVMe|tier.usage).
NVME_READ_BANDWIDTH = "mem:NVMe|bandwidth.read_latest"
# Host stat: read latency of the NVMe memory tier, in microseconds. Confirmed on VCF Operations 9.1.1.
NVME_READ_LATENCY = "mem:NVMe|latency.read_latest"

# 1 MB holds 256 pages of 4 KB.
PAGES_PER_MB = 256
SECONDS_PER_MICROSECOND = 1e-6

# The stats Memory Wait reads from each VM, and from each host.
VM_STATS = [MEMORY_CONTENTION, NVME_READ_BANDWIDTH]
HOST_STATS = [NVME_READ_LATENCY]


class VmMemoryContext(NamedTuple):
    """What the NVMe wait of a VM needs besides its own stats: its vCPUs and its host."""
    vcpus: Optional[float]
    host_id: Optional[str]          # VCF Operations resource id of the host the VM runs on


def nvme_wait_pct(bandwidth_mbps: float, host_latency_us: float, vcpus: float) -> Optional[float]:
    """The share of the VM's vCPU time spent waiting for pages fetched from the NVMe tier. None without vCPUs."""
    if not vcpus or vcpus <= 0:
        return None
    fetches_per_second = bandwidth_mbps * PAGES_PER_MB
    return fetches_per_second * host_latency_us * SECONDS_PER_MICROSECOND / vcpus * 100.0


def memory_wait_pct(
    vm_stats: Dict[str, float], vcpus: Optional[float], host_latency_us: Optional[float]
) -> Optional[float]:
    """Memory Contention plus NVMe wait. None when the VM has no Memory Contention: nothing is known about it."""
    if MEMORY_CONTENTION not in vm_stats:
        return None
    wait = vm_stats[MEMORY_CONTENTION]
    if NVME_READ_BANDWIDTH in vm_stats and host_latency_us is not None:
        nvme = nvme_wait_pct(vm_stats[NVME_READ_BANDWIDTH], host_latency_us, vcpus or 0)
        if nvme is not None:
            wait += nvme
    return wait
