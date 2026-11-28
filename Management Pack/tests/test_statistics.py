#  Copyright 2026 VCF Operations vCommunity Management Pack
"""Each KPI row reads the statistic its Agent E2 catalog interval states (R-ADP-008, T-ADP-008b).

A row whose catalog limits are for 20s reads a 20-second peak, a stat whose key contains "20_sec_peak". A row whose
limits are for 5m reads no 20-second peak. The interval of each row is its Metric.interval; the workspace's KPI
definitions check compares it with the catalog. The stats a row reads are found by handing its value function a
recording set of stats, so the test reads the code and no copy of it.

Run from the "Management Pack" folder:  python -m pytest tests
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from metrics.cluster import cluster_performance_metrics, cluster_risk_metrics, cluster_consumption_metrics
from metrics.host import esxi_performance_metrics
from metrics.vm import contention_by_vms, guest_os_performance_metrics, memory_wait, vm_performance_metrics

KPI_MODULES = {
    "Cluster Performance": cluster_performance_metrics,
    "ESXi Performance": esxi_performance_metrics,
    "VM Performance": vm_performance_metrics,
    "Guest OS Performance": guest_os_performance_metrics,
    "Cluster Risk": cluster_risk_metrics,
    "Cluster Consumption": cluster_consumption_metrics,
}

# 20-second peak keys whose key does not contain "20_sec_peak". net|droppedTxPct_max is VCF Operations' Peak
# Transmitted Packet Dropped within collection cycle (Q-WS-137, ASSUMPTION-8 in the workspace's brief).
# Each entry must be read by a 20s row: an entry no row reads fails the test.
PEAK_KEYS_WITHOUT_20_SEC_PEAK = {"net|droppedTxPct_max"}


def is_20_second_peak(key):
    return "20_sec_peak" in key or key in PEAK_KEYS_WITHOUT_20_SEC_PEAK


class RecordingStats(dict):
    """A set of VM stats that records every key a row asks for, and answers 1.0."""

    def __init__(self):
        super().__init__()
        self.read = set()

    def get(self, key, default=None):
        self.read.add(key)
        return 1.0

    def __getitem__(self, key):
        self.read.add(key)
        return 1.0

    def __contains__(self, key):
        self.read.add(key)
        return True


def stats_read(value_function):
    stats = RecordingStats()
    value_function(stats)
    return stats.read


def rows_with_stats():
    """(KPI, Metric, the stats it reads) for every row that reads one VM's stats."""
    out = []
    for row in vm_performance_metrics.ROWS:
        out.append(("VM Performance", row.metric, stats_read(row.value)))
    for row in guest_os_performance_metrics.ROWS:
        out.append(("Guest OS Performance", row.metric, stats_read(row.value)))
    for rows in contention_by_vms.VM_CONTENTION:
        read = set(memory_wait.VM_STATS) if rows.stat == contention_by_vms.MEMORY_WAIT_STAT else {rows.stat}
        for kpi in ("Cluster Performance", "ESXi Performance"):
            out.append((kpi, rows.worst, read))
            out.append((kpi, rows.percentile_90, read))
    return out


@pytest.mark.parametrize("kpi", sorted(KPI_MODULES))
def test_every_row_records_its_interval(kpi):
    for metric in KPI_MODULES[kpi].METRICS:
        assert metric.interval in ("20s", "5m"), f"{kpi}: {metric.name} has interval {metric.interval!r}"


def test_every_row_that_reads_vm_stats_is_covered():
    covered = {(kpi, metric.name) for kpi, metric, _ in rows_with_stats()}
    for kpi in ("VM Performance", "Guest OS Performance"):
        assert {(kpi, m.name) for m in KPI_MODULES[kpi].METRICS} <= covered
    for kpi in ("Cluster Performance", "ESXi Performance"):
        names = {m.name for m in contention_by_vms.VM_CONTENTION_METRICS}
        assert {(kpi, n) for n in names} <= covered


@pytest.mark.parametrize("kpi,metric,read", rows_with_stats(), ids=lambda v: getattr(v, "name", None) or str(v))
def test_a_row_reads_the_statistic_of_its_interval(kpi, metric, read):
    peaks = sorted(s for s in read if is_20_second_peak(s))
    if metric.interval == "5m":
        assert not peaks, f"{kpi}: {metric.name} is 5m and reads the 20-second peak {peaks}"
    else:
        assert peaks, f"{kpi}: {metric.name} is 20s and reads {sorted(read)}, no 20-second peak"


def test_every_listed_peak_key_is_read_by_a_20s_row():
    read_by_20s = set().union(*(read for _, metric, read in rows_with_stats() if metric.interval == "20s"))
    unused = PEAK_KEYS_WITHOUT_20_SEC_PEAK - read_by_20s
    assert not unused, f"no 20s row reads {sorted(unused)}: delete it from PEAK_KEYS_WITHOUT_20_SEC_PEAK"
