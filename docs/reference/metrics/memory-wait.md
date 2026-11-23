# Memory Wait

**Memory Wait** is the share of a VM's time spent waiting for memory, in %. It is Memory Contention plus NVMe wait:

```
Memory Wait = Memory Contention + NVMe wait
```

It is a row of [VM Performance](vm-performance.md) (**Memory Wait**), and the memory rows of [Cluster Performance](cluster-performance.md) and [ESXi Performance](esxi-performance.md) (the worst VM and the 90th percentile of the VMs' Memory Wait).

Code: [`Management Pack/app/metrics/vm/memory_wait.py`](../../../Management%20Pack/app/metrics/vm/memory_wait.py)

## Why a new metric

Memory tiering keeps a VM's cold pages on an NVMe device. When a vCPU touches one of them, it waits for the whole NVMe read. The vSphere Memory Contention counter is unaware of memory tiering: it does not count these fetches. A VM that waits on NVMe all day can therefore show a Memory Contention near 0, and a KPI built on Memory Contention alone would score it as healthy.

Memory Wait adds the missing part. The VM does not care where it waits for memory, so the two waits are summed and read like CPU Ready: the share of the VM's vCPU time spent waiting. The limits are those of Memory Contention.

On a host without memory tiering, the NVMe wait is 0 and Memory Wait equals Memory Contention.

## How it is calculated

Memory Contention is the 20-second peak `mem|20_sec_peak_host_contentionPct`. No counter gives the NVMe wait, so it is calculated with Little's law (the items in flight are the arrival rate times the time each takes):

```
NVMe wait (%) = VM NVMe read bandwidth (MB/s) × 256 pages per MB × NVMe read latency of the host (s) ÷ VM vCPUs × 100
```

- 1 MB holds 256 pages of 4 KB, so `MB/s × 256` is the page fetches per second.
- Times the read latency is the number of vCPUs frozen at any moment. Divided by the VM's vCPUs it is the share of its vCPU time.
- Example: a VM of 8 vCPUs reads 6 MB/s from NVMe on a host with a read latency of 290 µs. 6 × 256 = 1,536 fetches per second, times 0.00029 s = 0.445 vCPUs frozen, divided by 8 = 5.57 %. Its Memory Contention is 0, and its Memory Wait is 5.57, in red.

| Input | VCF Operations stat | Object |
| :--- | :--- | :--- |
| Memory Contention | `mem\|20_sec_peak_host_contentionPct` | VM |
| NVMe read bandwidth (MB/s) | `mem:NVMe\|bandwidth.read_latest` | VM. Not checked on a live VCF Operations yet. |
| NVMe read latency (µs) | `mem:NVMe\|latency.read_latest` | The host the VM runs on |
| vCPUs | `config\|hardware\|numCpu` | VM property |

## Metric keys

The memory rows of Cluster Performance and ESXi Performance keep their keys `Worst VM Memory Latency` and `90th Percentile VM Memory Latency`, by design: the keys date from before NVMe wait was scored. VCF Operations treats a new key as a new metric, without history, and the dashboards, views and reports that read the old key would go empty. So the key stays and the label says memory wait: "Worst memory wait among all VMs", "90th percentile memory wait among VMs" (and "... among VMs on the host" on ESXi Performance). The VM Performance row is new, so its key is `Memory Wait`.

## Known limitations

- **NVMe wait is calculated, not measured.** One 4 KB page per fetch is assumed. With prefetch or a large page there are fewer fetches than `MB/s × 256`, and the formula overstates the wait.
- **The host latency stands in for the VM's.** No counter gives the NVMe read latency per VM.
- **Mixed time base.** Memory Contention is a 20-second peak, the NVMe inputs are latest values. The NVMe part understates a burst.
- **A missing input leaves Memory Contention alone.** NVMe read latency is statistics level 3 and read bandwidth level 2. When one is not collected, or the VM's host or vCPU count is unknown, Memory Wait is the Memory Contention and understates the wait on a tiered host. The log says nothing: a host without tiering has no NVMe stats either.
- **vMotion.** The pre-copy of a vMotion reads the cold pages of the migrating VM from NVMe. If these reads count in the VM's NVMe read bandwidth, the VM's Memory Wait can turn red during a host evacuation although nothing in the guest waits on them. Not known whether they count.
- **A later release.** If a later vSphere release counts the NVMe fetches in Memory Contention, the sum counts the wait twice.
- **The stat of the NVMe read bandwidth has not been checked on a live system.** If its key is wrong, Memory Wait is the Memory Contention alone.
