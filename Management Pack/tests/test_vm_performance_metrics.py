#  Copyright 2026 VCF Operations vCommunity Management Pack
"""Worked examples for the VM Performance KPI. They double as documentation.

Run from the "Management Pack" folder:  python -m pytest tests
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from metrics.vm import vm_performance_metrics as vp
from metrics.vm import guest_os_performance_metrics as go
from metrics.vm import memory_wait as mw
from fakes import FakeSuiteApi, FakeObject

# A VM with nothing wrong: no contention, CPU Run low, nothing compressed or swapped.
HEALTHY = {
    **{stat_key: 0.0 for stat_key in vp.SOURCE_STATS.values()},
    mw.MEMORY_CONTENTION: 0.0,
    vp.MEM_COMPRESSED: 0.0,
    vp.MEM_SWAPPED: 0.0,
    vp.GUEST_USED_MEMORY: 4000000.0,
}


def collect(vm_stats):
    vm_obj = FakeObject("vm-1")
    vp.collect_vm_performance_metrics(vm_obj, "VM 1", vm_stats)
    return {key.split("|")[-1]: value for key, value in vm_obj.metrics.items()}


# --- The table --------------------------------------------------------------

def test_limits_match_the_source_table():
    # docs/reference/metrics/formula/vm-performance.png
    limits = {m.name: (m.green, m.yellow, m.orange, m.zero_at, m.skip_when_green) for m in vp.METRICS}
    assert limits["CPU Co-Stop"] == (1, 2, 4, 8, False)
    assert limits["CPU Ready"] == (2, 4, 8, 16, False)
    assert limits["CPU Overlap"] == (0.5, 1, 2, 4, True)            # green is "Excluded"
    assert limits["Memory Wait"] == (0.5, 1, 2, 4, False)
    assert limits["Disk Latency"] == (10, 20, 40, 80, False)
    assert limits["Network Dropped Tx"] == (0, 0.5, 1, 2, True)     # green is "Excluded", exactly 0
    assert limits["CPU Run"] == (95, 97, 99, 100, True)            # green is "Excluded"
    assert limits["Memory Ballooned"] == (2, 4, 8, 16, False)
    assert limits["Memory Zip Swap"] == (0.25, 0.5, 1, 2, False)


# --- Sub-metric formulas ----------------------------------------------------

def test_every_sub_metric_has_a_value():
    assert set(vp.vm_performance_values(HEALTHY)) == {metric.name for metric in vp.METRICS}
    assert None not in vp.vm_performance_values(HEALTHY).values()


def test_memory_zip_swap():
    stats = {vp.MEM_COMPRESSED: 10.0, vp.MEM_SWAPPED: 10.0, vp.GUEST_USED_MEMORY: 1000.0}
    assert vp.memory_zip_swap_pct(stats) == 2.0                              # 20 / 1000
    assert vp.memory_zip_swap_pct({**stats, vp.GUEST_USED_MEMORY: 0.0}) is None
    assert vp.memory_zip_swap_pct({vp.MEM_COMPRESSED: 10.0}) is None         # stats missing


# --- The KPI ----------------------------------------------------------------

def test_healthy_vm_scores_100_and_publishes_only_what_the_vm_does_not_have():
    assert collect(HEALTHY) == {"Memory Wait": 0.0, "Memory Zip Swap": 0.0, vp.KPI_KEY: 100.0}


# In HEALTHY, CPU Overlap, Network Dropped Tx and CPU Run are 0, in their excluded green, so they are left out.

def test_one_red_metric_is_not_hidden_by_five_good_ones():
    # CPU Ready = 10 is a quarter of the way through red (8 to 16): it scores 18.75 with weight 9.51.
    # The other five that count score 100 with weight 1.
    # KPI = (5 x 100 + 18.75 x 9.51) / (5 + 9.51) = 46.74. A plain average would give 86.5.
    assert collect({**HEALTHY, "cpu|20_sec_peak_readyPct": 10.0})[vp.KPI_KEY] == 46.74


def test_cpu_run_counts_only_above_95_percent():
    # Below 95 % CPU Run is in its excluded green: left out, not scored 100.
    assert collect({**HEALTHY, "cpu|net_run": 90.0})[vp.KPI_KEY] == 100.0
    # 98 % is halfway through orange (97 to 99): it scores 37.5 with weight 5.66.
    # KPI = (6 x 100 + 37.5 x 5.66) / (6 + 5.66) = 69.67
    assert collect({**HEALTHY, "cpu|net_run": 98.0})[vp.KPI_KEY] == 69.67


def test_any_dropped_packet_is_yellow_and_counts():
    # 0.25 % dropped is halfway through yellow (0 to 0.5): it scores 62.5 with weight 2.83.
    # KPI = (6 x 100 + 62.5 x 2.83) / (6 + 2.83) = 87.99
    assert collect({**HEALTHY, "net|droppedTxPct_max": 0.25})[vp.KPI_KEY] == 87.99


def test_disk_latency_uses_the_new_limits():
    # 30 ms is halfway through orange (20 to 40): it scores 37.5 with weight 5.66.
    # KPI = (5 x 100 + 37.5 x 5.66) / (5 + 5.66) = 66.82
    assert collect({**HEALTHY, "virtualDisk|20_sec_peak_totalLatency_average": 30.0})[vp.KPI_KEY] == 66.82


# --- Memory Wait: Memory Contention plus NVMe wait --------------------------

def collect_with_nvme(vm_stats, vcpus, latency_us):
    vm_obj = FakeObject("vm-1")
    vp.collect_vm_performance_metrics(vm_obj, "VM 1", vm_stats, vcpus, latency_us)
    return {key.split("|")[-1]: value for key, value in vm_obj.metrics.items()}


def test_memory_wait_adds_the_nvme_wait_to_memory_contention():
    # 6 MB/s x 256 pages = 1,536 fetches per second, each 290 us: 0.445 vCPU frozen on average, of 8 vCPUs: 5.57 %.
    # Memory Contention is 0 (it does not count NVMe fetches), so Memory Wait is the NVMe wait alone, red (above 4).
    stats = {**HEALTHY, mw.NVME_READ_BANDWIDTH: 6.0}
    assert collect_with_nvme(stats, 8, 290.0)["Memory Wait"] == 5.57
    assert collect_with_nvme({**stats, mw.MEMORY_CONTENTION: 0.5}, 8, 290.0)["Memory Wait"] == 6.07


def test_memory_wait_on_a_host_without_memory_tiering_is_memory_contention():
    # No NVMe stats, no host latency: nothing to add.
    assert collect_with_nvme({**HEALTHY, mw.MEMORY_CONTENTION: 0.7}, 8, None)["Memory Wait"] == 0.7
    assert collect_with_nvme({**HEALTHY, mw.MEMORY_CONTENTION: 0.7}, 8, 290.0)["Memory Wait"] == 0.7


def test_memory_wait_without_vcpus_is_memory_contention_alone():
    stats = {**HEALTHY, mw.NVME_READ_BANDWIDTH: 6.0, mw.MEMORY_CONTENTION: 0.7}
    assert collect_with_nvme(stats, None, 290.0)["Memory Wait"] == 0.7


def test_nvme_wait_formula_is_littles_law():
    assert round(mw.nvme_wait_pct(6.0, 290.0, 8), 2) == 5.57
    assert mw.nvme_wait_pct(6.0, 290.0, 0) is None
    assert mw.memory_wait_pct({}, 8, 290.0) is None          # no Memory Contention: nothing is known


def test_a_vm_waiting_on_nvme_lowers_vm_performance():
    # Memory Wait 5.57 % is past the end of red for a VM (4): it scores 0 with weight 16.
    # The other five that count score 100 with weight 1: KPI = 5 x 100 / (5 + 16) = 23.81.
    stats = {**HEALTHY, mw.NVME_READ_BANDWIDTH: 6.0}
    assert collect_with_nvme(stats, 8, 290.0)[vp.KPI_KEY] == 23.81
    assert collect(stats)[vp.KPI_KEY] == 100.0               # the same VM without the NVMe inputs


# --- Missing data -----------------------------------------------------------

def test_vm_without_tools_is_scored_on_the_stats_it_has():
    no_tools = {key: value for key, value in HEALTHY.items() if key != vp.GUEST_USED_MEMORY}
    published = collect({**no_tools, "cpu|20_sec_peak_readyPct": 10.0})
    # Memory Zip Swap needs a Tools stat, so it has no data. Three more are in their excluded green.
    # That leaves four at 100 and CPU Ready at 18.75 with weight 9.51.
    # KPI = (4 x 100 + 18.75 x 9.51) / (4 + 9.51) = 42.80
    assert published == {"Memory Wait": 0.0, vp.KPI_KEY: 42.8}


def test_vm_with_no_stats_publishes_nothing():
    assert collect({}) == {}


# --- Reading stats ----------------------------------------------------------

def test_stats_of_both_vm_kpis_are_read_for_all_vms_in_one_go():
    guest_stats = {go.GUEST_DISK_QUEUE: 3.0, go.GUEST_CPU_QUEUE: 1.0}
    api = FakeSuiteApi({"vm-1": {key: [value] for key, value in {**HEALTHY, **guest_stats}.items()}, "vm-2": {}})
    stats = vp.read_vm_performance_stats(api, ["vm-1", "vm-2"])
    assert api.requests == 1
    assert stats["vm-1"] == {**HEALTHY, **guest_stats}
    assert stats["vm-2"] == {}


def test_failed_stats_call_gives_no_stats():
    api = FakeSuiteApi({"vm-1": {key: [value] for key, value in HEALTHY.items()}}, status_code=500)
    assert vp.read_vm_performance_stats(api, ["vm-1"]) == {}
