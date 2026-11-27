#  Copyright 2026 VCF Operations vCommunity Management Pack
"""The keys the adapter definition declares equal the keys the collectors publish, for each object type.

T-ADP-007a, of R-ADP-007 in spec/requirements/adapter.md. The test builds the definition (definition.py), runs whole
collection cycles of adapter.collect() against a fake vCenter and the fake VCF Operations of tests/fakes.py, and
compares the two key sets of each object type: the same groups, the same spelling, metric or property, and an instance
where the group is instanced. A key that is published but not declared, or declared but never published, fails.

The fake vCenter below has one of everything: a cluster with two hosts, a Windows VM, a VM template, a datastore,
licenses, NICs, HBAs, software packages, content libraries, and one entry in each configuration file. In the fake VCF
Operations every stat and property has a value. Two cycles run, because two calculations are due in different cycles:
the Periodic Cluster Check of the clusters, then the Cluster Delta counts on vSphere World, which wait for it.

Run from the "Management Pack" folder:  python -m pytest tests
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

import pytest
from pyVmomi import vim

import adapter
from collectors.cluster import collectClusterData
from collectors.datastore import collectDatastoreData
from collectors.host import collectHostData
from collectors.library import collectLibraryData
from collectors.vm import collectVMData
from constants import main as constants
from definition import get_adapter_definition
from metrics.container import business_app_performance as bap
from metrics.vcenter import vcenter_port_groups
from metrics.world import cluster_close_changes
from metrics.cluster import periodic_cluster_check
from utils import guest_ops
from fakes import FakeResource, FakeVcfOperations

VMWARE = constants.VCENTER_ADAPTER_KIND

# The object type of the definition that declares the keys of each resource kind the collectors publish on.
DECLARED_ON = {
    (VMWARE, "ClusterComputeResource"): "Cluster Compute Resource",
    (VMWARE, "HostSystem"): "Host System",
    (VMWARE, "VirtualMachine"): "Virtual Machine",
    (VMWARE, "Datastore"): "vCommunity-Datastore",
    (VMWARE, "VMwareAdapter Instance"): "vCenter",
    (VMWARE, "vSphere World"): "vSphere World",
    (VMWARE, "Datacenter"): "Datacenter",
    **{(bap.CONTAINER_ADAPTER_KIND, kind): kind for kind, _, _ in bap.DEFINED_ON},
    **{(constants.ADAPTER_KIND, kind): kind for kind in ("Content Library", "Library Item", "VM Template")},
}

# Groups whose attribute names are the entries of a configuration file, chosen per Adapter Instance. No fixed key can
# be declared for them: the definition declares the group, and any attribute published in it matches.
CONFIGURED_GROUPS = {
    "Host System": ["vCommunity|Configuration|Advanced System Settings"],
    "Virtual Machine": ["vCommunity|Configuration|Advanced Parameters", "vCommunity|Options"],
}
ANY_ATTRIBUTE = "<any entry of the configuration file>"


# ---- the declared keys -----------------------------------------------------------------------------------------


def declared_keys():
    """{object type: {(key, "metric" or "property")}}, and {object type: {group path: instance required}} for the
    instanced groups. A key is the path of group keys and the attribute key, joined with |."""
    keys, instanced = {}, {}
    for object_type in get_adapter_definition().to_json()["object_types"]:
        type_keys = keys.setdefault(object_type["key"], set())
        type_instanced = instanced.setdefault(object_type["key"], {})
        for group_path, group in groups_of(object_type):
            if group["instanced"]:
                type_instanced[group_path] = group["instance_required"]
            if group_path in CONFIGURED_GROUPS.get(object_type["key"], []):
                type_keys.add((f"{group_path}|{ANY_ATTRIBUTE}", "property"))
            for attribute in group["attributes"]:
                kind = "property" if attribute["is_property"] else "metric"
                type_keys.add((f"{group_path}|{attribute['key']}", kind))
    return keys, instanced


def groups_of(node, path=""):
    """(group path, group) of every group under a node of the definition, at any depth."""
    for group in node.get("groups", []):
        group_path = f"{path}|{group['key']}" if path else group["key"]
        yield group_path, group
        yield from groups_of(group, group_path)


# ---- the published keys ----------------------------------------------------------------------------------------


def published_keys(objects):
    """{object type: {(key, kind)}} of what the objects carry, with the instance names removed, and {object type:
    {(group path, True when the key names an instance of that group)}} for every group of every key."""
    keys, instances = {}, {}
    for obj in objects:
        key = obj.get_key()
        object_type = DECLARED_ON.get((key.adapter_kind, key.object_kind), f"{key.adapter_kind}:{key.object_kind}")
        body = obj.get_json()
        for kind, items in (("metric", body["metrics"]), ("property", body["properties"])):
            for item in items:
                path, groups = split_instances(item["key"])
                keys.setdefault(object_type, set()).add((configured(object_type, path), kind))
                instances.setdefault(object_type, set()).update(groups)
    return keys, instances


def split_instances(key):
    """"vCommunity|Network|Device:vmnic0|MAC" -> ("vCommunity|Network|Device|MAC", {("vCommunity|Network|Device", True)}),
    and ("vCommunity|Network", False) for the groups named without an instance."""
    segments = key.split("|")
    path, groups = [], set()
    for segment in segments[:-1]:
        name, separator, _ = segment.partition(":")
        path.append(name)
        groups.add(("|".join(path), bool(separator)))
    return "|".join(path + segments[-1:]), groups


def configured(object_type, path):
    for group in CONFIGURED_GROUPS.get(object_type, []):
        if path.startswith(group + "|"):
            return f"{group}|{ANY_ATTRIBUTE}"
    return path


# ---- the fake vCenter ------------------------------------------------------------------------------------------

NOW = datetime.now(timezone.utc)
VCENTER_HOST = "vcenter.test"
VCENTER_UUID = "vc-uuid-1"
CLUSTER_NAME = "Cluster 1"
DATACENTER_NAME = "Datacenter 1"
PRESENTED_THUMBPRINT = "ab" * 32

FILES = {
    "esxi_settings": "<advancedSettings>Misc.HostName</advancedSettings>",
    "esxi_packages": "<packages>nmlx5-core</packages>",
    "vm_parameters": "<parameters>isolation.tools.copy.disable</parameters>",
    "vm_options": "<options>config.cpuHotAddEnabled</options>",
    "services": "<services>Spooler</services>",
    "events": "<Events><Log Name=\"System\"><EventID>41</EventID></Log></Events>",
}

SETTINGS = {
    constants.HOST_IDENTIFIER: VCENTER_HOST,
    constants.PORT_IDENTIFIER: "443",
    "esxi_adv_settings_config_file": "esxi_settings",
    "esxi_vib_driver_config_file": "esxi_packages",
    "vm_adv_settings_config_file": "vm_parameters",
    "vm_configuration_config_file": "vm_options",
    "win_service_config_file": "services",
    "win_event_config_file": "events",
    "serviceMonitoring": "Enabled",
    "winEventMonitoring": "Enabled",
}
CREDENTIALS = {constants.USER_CREDENTIAL: "reader", constants.PASSWORD_CREDENTIAL: "x",
               "winUser": "windows-reader", "winPass": "x"}


class FakeAdapterInstance:
    def __init__(self, suite_api):
        self.suite_api_client = suite_api

    def get_identifier_value(self, name, default=None):
        return SETTINGS.get(name, default)

    def get_credential_value(self, name):
        return CREDENTIALS.get(name)


def vmware(resource_id, kind, name, moid=None, **kwargs):
    identifiers = {"VMEntityObjectID": moid} if moid else {}
    identifiers.update(kwargs.pop("identifiers", {}))
    return FakeResource(resource_id, VMWARE, kind, name, identifiers, **kwargs)


def vcf_operations(old_keys):
    host_properties = {
        "summary|parentCluster": CLUSTER_NAME, "summary|parentDatacenter": DATACENTER_NAME,
        "hardware|cpuInfo|numCpuCores": "32", "config|hyperThread|active": "true", "config|hyperThread|available": "true",
        "runtime|connectionState": "connected", "runtime|maintenanceState": "notInMaintenance",
        "runtime|powerState": "poweredOn",
    }
    vm_properties = {
        "summary|runtime|powerState": "Powered On", "config|hardware|numCpu": "4", "config|hardware|memoryKB": "8388608",
        "config|cpuAllocation|shares|shares": "4000", "config|memoryAllocation|shares|shares": "81920",
        "summary|guest|toolsRunningStatus": "guestToolsNotRunning", "summary|guest|toolsVersionStatus2": "guestToolsCurrent",
    }
    resources = [
        vmware("ai-1", "VMwareAdapter Instance", VCENTER_HOST,
               identifiers={"VCURL": VCENTER_HOST, "VMEntityVCID": VCENTER_UUID}),
        vmware("world-1", "vSphere World", "vSphere World"),
        vmware("dc-1", "Datacenter", DATACENTER_NAME, "datacenter-1"),
        vmware("cluster-1", "ClusterComputeResource", CLUSTER_NAME, "domain-c1"),
        vmware("host-1", "HostSystem", "esxi-1", "host-11", properties=host_properties),
        vmware("host-2", "HostSystem", "esxi-2", "host-12", properties=host_properties),
        vmware("vm-1", "VirtualMachine", "win-01", "vm-101",
               properties={**vm_properties, "summary|parentHost": "esxi-1"}),
        vmware("vm-2", "VirtualMachine", "linux-01", "vm-102",
               properties={**vm_properties, "summary|parentHost": "esxi-2"}),
        vmware("template-1", "VirtualMachine", "tpl-ubuntu", "vm-103",
               properties={**vm_properties, "summary|runtime|powerState": "Powered Off"}),
        vmware("ds-1", "Datastore", "datastore-01", "datastore-1"),
        vmware("rp-1", "ResourcePool", "pool-1", "resgroup-1", parents=[("ClusterComputeResource", "cluster-1")]),
        vmware("rp-2", "ResourcePool", "pool-2", "resgroup-2", parents=[("ResourcePool", "rp-1")]),
        FakeResource("ent-1", bap.CONTAINER_ADAPTER_KIND, bap.ENTERPRISE_KIND, "Enterprise",
                     children=[(bap.APPLICATION_KIND, "app-1")]),
        FakeResource("app-1", bap.CONTAINER_ADAPTER_KIND, bap.APPLICATION_KIND, "Shop",
                     children=[(bap.TIER_KIND, "tier-1"), (bap.NAMESPACE_KIND, "ns-1")]),
        FakeResource("tier-1", bap.CONTAINER_ADAPTER_KIND, bap.TIER_KIND, "Web", children=[(bap.VM_KIND, "vm-1")]),
        FakeResource("ns-1", "KubernetesAdapter", bap.NAMESPACE_KIND, "shop"),
    ]
    return FakeVcfOperations(resources, files=FILES, old_keys=old_keys,
                             instances={"net|speed": ["vmnic0"], "net|configuredSpeed": ["vmnic0"]})


def ref(moid, name, **kwargs):
    return SimpleNamespace(_moId=moid, name=name, **kwargs)


def entry(obj, props):
    return SimpleNamespace(obj=obj, propSet=[SimpleNamespace(name=name, val=value) for name, value in props.items()])


def cluster_entries():
    summary = SimpleNamespace(currentEVCModeKey="intel-icelake", drsScore=90)
    configuration_ex = SimpleNamespace(
        proactiveDrsConfig=SimpleNamespace(enabled=True),
        drsConfig=SimpleNamespace(option=[SimpleNamespace(key="MaxVcpusPerCore", value="8")]),
        dpmConfigInfo=SimpleNamespace(hostPowerActionRate=3),
    )
    das = "configuration.dasConfig"
    tools = f"{das}.defaultVmSettings.vmToolsMonitoringSettings"
    return [entry(ref("domain-c1", CLUSTER_NAME), {
        "name": CLUSTER_NAME, "summary": summary, "configurationEx": configuration_ex,
        f"{das}.enabled": True, f"{das}.hostMonitoring": "enabled",
        f"{das}.defaultVmSettings.isolationResponse": "powerOff",
        f"{das}.defaultVmSettings.restartPriority": "medium",
        f"{das}.defaultVmSettings.vmComponentProtectionSettings.vmStorageProtectionForAPD": "restartConservative",
        f"{das}.defaultVmSettings.vmComponentProtectionSettings.vmStorageProtectionForPDL": "restartAggressive",
        f"{das}.vmMonitoring": "vmMonitoringOnly", f"{das}.hBDatastoreCandidatePolicy": "allFeasibleDsWithUserPreference",
        f"{tools}.failureInterval": 30, f"{tools}.maxFailureWindow": 3600, f"{tools}.maxFailures": 3,
        f"{tools}.minUpTime": 120,
        "configuration.drsConfig.enabled": True, "configuration.drsConfig.enableVmBehaviorOverrides": True,
        "configuration.drsConfig.scaleDescendantsShares": "scaleCpuAndMemoryShares",
        "configStatus": "green", "summary.numEffectiveHosts": 2, "overallStatus": "green",
    })]


class FakeImageConfigManager:
    def installDate(self):
        return NOW - timedelta(days=400)

    def fetchSoftwarePackages(self):
        return [SimpleNamespace(name="nmlx5-core", version="4.23", acceptanceLevel="VMwareCertified",
                                maintenanceModeRequired=True, summary="Mellanox driver", type="bootbank",
                                vendor="MEL")]


def host_entries():
    network = SimpleNamespace(
        dnsConfig=SimpleNamespace(dhcp=False, searchDomain=["corp.test"]),
        pnic=[SimpleNamespace(device="vmnic0", driverVersion="4.23", firmwareVersion="16.35", mac="00:50:56:00:00:01",
                              linkSpeed=SimpleNamespace(speedMb=25000, duplex=True), pci="0000:3b:00.0",
                              wakeOnLanSupported=False)],
    )
    pci = [SimpleNamespace(id="0000:3b:00.0", vendorName="Mellanox", deviceName="ConnectX-5", vendorId=0x15b3,
                           deviceId=0x1017, subVendorId=0x15b3)]
    hba = [SimpleNamespace(device="vmhba0", key="key-vim.host.BlockHba-vmhba0", bus=59, model="Dell BOSS",
                           pci="0000:3b:00.1", status="online", storageProtocol="scsi")]
    options = [SimpleNamespace(key="Misc.HostName", value="esxi"), SimpleNamespace(key="VMFS3.UseATSForHBOnVMFS5", value=1),
               SimpleNamespace(key="VMFS3.HardwareAcceleratedLocking", value=1)]
    return [entry(ref(moid, name), {
        "name": name, "runtime.connectionState": "connected", "configManager.imageConfigManager": FakeImageConfigManager(),
        "config.network": network, "hardware.pciDevice": pci, "capability.storageVMotionSupported": True,
        "config.dateTimeInfo.timeZone.description": "UTC", "config.dateTimeInfo.timeZone.gmtOffset": 0,
        "config.dateTimeInfo.timeZone.name": "UTC", "hardware.biosInfo.vendor": "Dell Inc.",
        "runtime.bootTime": NOW - timedelta(days=30), "config.storageDevice.hostBusAdapter": hba, "config.option": options,
        "configStatus": "green", "summary.maxEVCModeKey": "intel-sapphirerapids",
    }) for moid, name in (("host-11", "esxi-1"), ("host-12", "esxi-2"))]


def vm_devices():
    controller = vim.vm.device.ParaVirtualSCSIController(key=1000, busNumber=0)
    nic = vim.vm.device.VirtualVmxnet3(key=4000, addressType="assigned",
                                       deviceInfo=vim.Description(label="Network adapter 1", summary="VM Network"),
                                       connectable=vim.vm.device.VirtualDevice.ConnectInfo(startConnected=True))
    disk = vim.vm.device.VirtualDisk(
        key=2000, controllerKey=1000, deviceInfo=vim.Description(label="Hard disk 1", summary="40 GB"),
        backing=vim.vm.device.VirtualDisk.FlatVer2BackingInfo(eagerlyScrub=False, split=False, writeThrough=False,
                                                              diskMode="persistent", fileName="[datastore-01] a.vmdk"),
        shares=vim.SharesInfo(level="normal", shares=1000),
    )
    return [controller, nic, disk]


def vm_entries():
    guest = SimpleNamespace(guestDetailedData="buildNumber='22631' cpeString='cpe:/o:microsoft' distroAddlVersion='x' "
                                              "distroName='Windows' distroVersion='11' kernelVersion='10.0' prettyName='Windows 11'")
    common = {
        "config.hardware.device": vm_devices(), "config.extraConfig": [SimpleNamespace(key="isolation.tools.copy.disable", value="TRUE")],
        "config.cpuHotAddEnabled": False,
        "config.bootOptions.bootDelay": 0, "config.bootOptions.bootRetryDelay": 10000,
        "config.bootOptions.bootRetryEnabled": False, "config.bootOptions.enterBIOSSetup": False,
        "config.changeVersion": "2026-11-01T00:00:00Z", "config.firmware": "efi", "config.flags.diskUuidEnabled": True,
        "config.latencySensitivity.level": "normal", "config.rebootPowerOff": False,
        "config.scheduledHardwareUpgradeInfo.scheduledHardwareUpgradeStatus": "none",
        "config.scheduledHardwareUpgradeInfo.upgradePolicy": "never", "config.scheduledHardwareUpgradeInfo.versionKey": "vmx-21",
        "config.vmOpNotificationTimeout": 30, "guest.guestState": "running", "runtime.consolidationNeeded": False,
        "runtime.dasVmProtection.dasProtected": True, "runtime.minRequiredEVCModeKey": "intel-merom",
        "config.tools.syncTimeWithHost": False, "config.tools.toolsUpgradePolicy": "manual", "guest.appState": "none",
        "guest.guestKernelCrashed": False, "guest.guestOperationsReady": True, "guest.guestStateChangeSupported": True,
        "guest.interactiveGuestOperationsReady": False, "config.numaInfo.vnumaOnCpuHotaddExposed": False,
        "config.cpuAllocation.shares.level": "normal", "configStatus": "green",
        "guest.customizationInfo.customizationStatus": "TOOLSDEPLOYPKG_SUCCEEDED",
        "summary.quickStats.guestHeartbeatStatus": "green", "summary.config.vmPathName": "[datastore-01] a/a.vmx",
        "config.memoryAllocation.shares.level": "normal", "guest": guest,
        "config.guestFullName": "Microsoft Windows 11", "config.version": "vmx-21", "summary.config.numCpu": 4,
        "summary.config.memorySizeMB": 8192, "summary.storage.committed": 40 * 1024 ** 3,
        "datastore": [SimpleNamespace(name="datastore-01")],
    }
    windows_guest = SimpleNamespace(toolsStatus="toolsOk", guestFamily="windowsGuest")
    linux_guest = SimpleNamespace(toolsStatus="toolsOk", guestFamily="linuxGuest")
    folder = SimpleNamespace(name="Templates")
    return [
        entry(ref("vm-101", "win-01", guest=windows_guest, parent=folder), {**common, "name": "win-01", "config.template": False}),
        entry(ref("vm-102", "linux-01", guest=linux_guest, parent=folder), {**common, "name": "linux-01", "config.template": False}),
        entry(ref("vm-103", "tpl-ubuntu", guest=linux_guest, parent=folder), {**common, "name": "tpl-ubuntu", "config.template": True}),
    ]


def datastore_entries():
    info = vim.host.VmfsDatastoreInfo(vmfs=vim.host.VmfsVolume(
        blockSizeMb=1, maxBlocks=63963136, vmfsUpgradable=False,
        extent=[vim.host.ScsiDisk.Partition(diskName="naa.600a0980383146", partition=1)]))
    return [entry(ref("datastore-1", "datastore-01"), {
        "name": "datastore-01", "summary.type": "VMFS", "info": info, "overallStatus": "green",
        "iormConfiguration.enabled": True, "iormConfiguration.congestionThreshold": 30,
    })]


VCENTER_OBJECTS = {
    vim.ClusterComputeResource: cluster_entries,
    vim.HostSystem: host_entries,
    vim.VirtualMachine: vm_entries,
    vim.Datastore: datastore_entries,
}


def retrieve_properties(content, object_type, paths):
    """The fake vCenter's objects of one type, with the requested paths that it has a value for."""
    wanted = set(paths) | {"name"}
    return [SimpleNamespace(obj=item.obj, propSet=[prop for prop in item.propSet if prop.name in wanted])
            for item in VCENTER_OBJECTS[object_type]()]


def vcenter_content():
    licenses = [SimpleNamespace(entityId=moid, assignedLicense=SimpleNamespace(
        name="VMware vSphere 9 Enterprise Plus", licenseKey="00000-00000-00000-00000-00000", editionKey="esx.vcf.cpuCore",
        properties=[SimpleNamespace(key="expirationDate", value=NOW + timedelta(days=200))])) for moid in ("host-11", "host-12")]
    option_manager = SimpleNamespace(QueryOptions=lambda name: [SimpleNamespace(value="10")])
    file_manager = SimpleNamespace(CreateTemporaryDirectory=lambda *args: "C:\\Windows\\Temp\\vcommunity")
    return SimpleNamespace(
        about=SimpleNamespace(instanceUuid=VCENTER_UUID, patchLevel="1", name="VMware vCenter Server", version="9.1.0"),
        licenseManager=SimpleNamespace(licenseAssignmentManager=SimpleNamespace(QueryAssignedLicenses=lambda: licenses)),
        setting=option_manager,
        guestOperationsManager=SimpleNamespace(processManager=SimpleNamespace(), fileManager=file_manager),
    )


GUEST_OUTPUT = {
    "Services.csv": '"Name","DisplayName","Status","StartType"\n"Spooler","Print Spooler","Running","Automatic"\n',
    "OSInfo.csv": '"Name","Version","BuildNumber","OSArchitecture","LastBootUpTime","ReleaseId"\n'
                  '"Windows 11","10.0.22631","22631","64-bit","2026-11-01","23H2"\n',
    "Event_Log.csv": '"Level","Event"\n"Error","Event 41: the system rebooted without cleanly shutting down"\n',
}


class FakeLibraryReader:
    """The vSphere Automation REST API of the fake vCenter: one subscribed library with one OVF item."""

    ANSWERS = {
        "/content/library": ["lib-1"],
        "/content/library/lib-1": {"id": "lib-1", "name": "cl-vks", "type": "SUBSCRIBED", "state_info": {"state": "ACTIVE"},
                                   "subscription_info": {"subscription_url": "https://lib.test/lib.json",
                                                         "automatic_sync_enabled": True}},
        "/content/library/item?library_id=lib-1": ["item-1"],
        "/content/library/item/item-1": {"id": "item-1", "name": "ubuntu", "type": "ovf", "size": 2 * 1024 ** 3,
                                         "cached": True, "security_compliance": True, "description": "Ubuntu",
                                         "version": "2", "content_version": "3", "last_modified_time": "2026-11-01",
                                         "last_sync_time": "2026-11-02", "source_id": "src-1",
                                         "certificate_verification_info": {"status": "VERIFIED"}},
    }

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def get(self, path):
        return self.ANSWERS[path]


@pytest.fixture
def fake_vcenter(monkeypatch):
    content = vcenter_content()
    monkeypatch.setattr(adapter, "_get_service_instance", lambda instance: SimpleNamespace(RetrieveContent=lambda: content))
    monkeypatch.setattr(adapter.tls, "presented_thumbprint", lambda host, port=443: PRESENTED_THUMBPRINT)
    for module in (collectClusterData, collectHostData, collectVMData, collectDatastoreData):
        monkeypatch.setattr(module, "retrieve_properties", retrieve_properties)
    monkeypatch.setattr(vcenter_port_groups, "read_port_group_names",
                        lambda content: {"datacenter-1": [["VM Network"], ["VM Network"], ["dvpg-web"]]})
    monkeypatch.setattr(collectLibraryData, "LibraryReader", FakeLibraryReader)
    monkeypatch.setattr(guest_ops, "transfer_file", lambda *args: True)
    monkeypatch.setattr(guest_ops, "run_powershell", lambda *args, **kwargs: None)
    monkeypatch.setattr(guest_ops, "create_temp_file", lambda *args: (True, "C:\\Windows\\Temp\\vcommunity\\events.xml"))
    monkeypatch.setattr(guest_ops, "file_exists", lambda *args: True)
    monkeypatch.setattr(guest_ops, "remove_temp_dir", lambda *args: None)
    monkeypatch.setattr(guest_ops, "read_guest_output",
                        lambda file_manager, vm, creds, path: GUEST_OUTPUT.get(path.rsplit("\\", 1)[1], ""))


def collect_twice():
    """The objects of two collection cycles: the first with the Periodic Cluster Check due, the second with the
    Cluster Delta counts due."""
    first = adapter.collect(FakeAdapterInstance(vcf_operations(old_keys=[f"vCommunity|{periodic_cluster_check.GROUP}|"])))
    second = adapter.collect(FakeAdapterInstance(vcf_operations(old_keys=[
        f"vCommunity|{cluster_close_changes.CLOSE_COUNT}", f"vCommunity|{cluster_close_changes.OPEN_COUNT}"])))
    for result in (first, second):
        assert result.get_json().get("errorMessage") is None, result.get_json()["errorMessage"]
    return list(first.objects.values()) + list(second.objects.values())


def differences(declared, declared_instanced, published, published_groups):
    found = []
    for object_type in sorted(set(declared) | set(published)):
        declared_keys_ = declared.get(object_type, set())
        published_keys_ = published.get(object_type, set())
        for key, kind in sorted(published_keys_ - declared_keys_):
            found.append(f"{object_type}: published, not declared: {kind} {key}")
        for key, kind in sorted(declared_keys_ - published_keys_):
            found.append(f"{object_type}: declared, never published: {kind} {key}")
        instanced = declared_instanced.get(object_type, {})
        for group, with_instance in sorted(published_groups.get(object_type, set())):
            if with_instance and group not in instanced:
                found.append(f"{object_type}: published with an instance, declared without: group {group}")
            if not with_instance and instanced.get(group):
                found.append(f"{object_type}: published without an instance, declared as instance required: group {group}")
    return found


def test_the_declared_keys_equal_the_published_keys_for_each_object_type(fake_vcenter, caplog):
    declared, declared_instanced = declared_keys()
    published, published_groups = published_keys(collect_twice())

    found = differences(declared, declared_instanced, published, published_groups)
    assert found == [], "\n".join(
        found + ["Warnings of the cycles:"] + [r.getMessage() for r in caplog.records if r.levelname in ("WARNING", "ERROR")])


def test_every_object_type_the_collectors_publish_on_is_declared(fake_vcenter):
    declared, _ = declared_keys()
    published, _ = published_keys(collect_twice())
    assert sorted(set(published) - set(declared)) == []
    # Every declared object type gets keys from some collector.
    assert sorted(set(declared) - set(published)) == []


def test_instance_names_are_split_from_the_group():
    assert split_instances("vCommunity|Network|Device:vmnic0|MAC") == (
        "vCommunity|Network|Device|MAC", {("vCommunity", False), ("vCommunity|Network", False),
                                          ("vCommunity|Network|Device", True)})
    assert split_instances("vCommunity|Configuration|SCSI Controllers|Count")[0] == "vCommunity|Configuration|SCSI Controllers|Count"
