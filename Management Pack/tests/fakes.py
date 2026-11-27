#  Copyright 2026 VCF Operations vCommunity Management Pack
"""A fake VCF Operations, shared by the KPI tests and by the test of a whole collection cycle."""
import json
import time

CYCLE_MS = 5 * 60 * 1000


class FakeResponse:
    def __init__(self, body, status_code=200, text=None):
        self.body = body
        self.status_code = status_code
        self.ok = status_code < 400
        self.text = text if text is not None else json.dumps(body)
        self.content = self.text

    def json(self):
        return self.body


class FakeSuiteApi:
    """A fake VCF Operations Suite API.

    samples:    {resource id: {stat key: [samples]}}, for the stats queries.
    properties: {resource id: {property key: value}}, for the properties query.
    resources:  {resource kind: [(resource id, name, MoRef id)]}, for the resources query.
    stale:      {resource id: [stat keys]} whose samples are an hour old. All other samples are current:
                the last one now, the others one 5-minute cycle apart.
    latest_at:  {resource id: {stat key: epoch ms}}: the time of the last sample of that stat, instead of now.
    """

    def __init__(self, samples=None, status_code=200, properties=None, resources=None, stale=None, latest_at=None):
        self.samples = samples or {}
        self.properties = properties or {}
        self.resources = resources or {}
        self.status_code = status_code
        self.requests = 0
        self.paths = []
        self.resource_queries = []
        self.stale = stale or {}
        self.latest_at = latest_at or {}

    def paged_post(self, path, key, json):
        self.paths.append(path)
        self.resource_queries.append(json)
        resource_list = [
            {"identifier": resource_id, "resourceKey": {"name": name, "resourceIdentifiers": [
                {"identifierType": {"name": "VMEntityObjectID"}, "value": moid}]}}
            for kind in json["resourceKind"] for resource_id, name, moid in self.resources.get(kind, [])
        ]
        return {key: resource_list}

    def post(self, path, json):
        self.requests += 1
        self.paths.append(path)
        if "propertyKeys" in json:
            return self._properties(json)
        values = []
        for resource_id in json["resourceId"]:
            stats = [
                {"statKey": {"key": key}, "timestamps": self._timestamps(resource_id, key, len(data)), "data": data}
                for key, data in self.samples.get(resource_id, {}).items() if self._requested(key, json["statKey"])
            ]
            values.append({"resourceId": resource_id, "stat-list": {"stat": stats}})
        return FakeResponse({"values": values}, self.status_code)

    def _timestamps(self, resource_id, key, count):
        end = self.latest_at.get(resource_id, {}).get(key)
        if end is None:
            end = time.time() * 1000 - (3600 * 1000 if key in self.stale.get(resource_id, []) else 0)
        return [end - (count - 1 - i) * CYCLE_MS for i in range(count)]

    @staticmethod
    def _requested(key, stat_keys):
        """Like VCF Operations: a requested stat also returns its instances, such as net:vmnic0|speed for net|speed."""
        group, _, rest = key.partition("|")
        return key in stat_keys or f"{group.split(':')[0]}|{rest}" in stat_keys

    def _properties(self, json):
        values = []
        for resource_id in json["resourceIds"]:
            contents = [
                {"statKey": key, "timestamps": [0], "values": [value]}
                for key, value in self.properties.get(resource_id, {}).items() if key in json["propertyKeys"]
            ]
            values.append({"resourceId": resource_id, "property-contents": {"property-content": contents}})
        return FakeResponse({"values": values}, self.status_code)


class FakeObject:
    """An SDK object. Like the real one, it has no get_id(): the resource id comes from utils/ops_stats.py."""

    def __init__(self, name):
        self.name = name
        self.metrics = {}
        self.properties = {}

    def with_metric(self, key, value):
        self.metrics[key] = value

    def with_property(self, key, value):
        self.properties[key] = value


class FakeMoRef:
    def __init__(self, mo_id, vm=(), host=()):
        self._moId = mo_id
        self.vm = list(vm)
        self.host = list(host)


class FakeResource:
    """One resource of the fake VCF Operations below: its id, adapter kind, resource kind, name and identifiers."""

    def __init__(self, resource_id, adapter_kind, kind, name, identifiers=None, properties=None, children=(),
                 parents=()):
        self.id = resource_id
        self.adapter_kind = adapter_kind
        self.kind = kind
        self.name = name
        self.identifiers = identifiers or {}
        self.properties = properties or {}      # {property key: value}; any other property key reads as "1"
        self.children = list(children)          # [(resource kind, id)], for the CHILD relationship
        self.parents = list(parents)            # [(resource kind, id)], for the PARENT relationship

    def key_json(self):
        return {
            "adapterKindKey": self.adapter_kind,
            "resourceKindKey": self.kind,
            "name": self.name,
            "resourceIdentifiers": [
                {"identifierType": {"name": name, "isPartOfUniqueness": True}, "value": value}
                for name, value in self.identifiers.items()
            ],
        }


class FakeVcfOperations:
    """A fake VCF Operations in which every resource listed exists and every stat and property asked for has a
    value, so that a whole collection cycle publishes everything it can. Used by tests/test_declared_keys.py.

    resources:    [FakeResource]. A resource query returns those of the requested adapter and resource kinds.
    files:        {configuration file name: its XML}, for api/configurations/files.
    old_keys:     stat key prefixes whose latest sample is three days old, so that a periodic calculation is due.
    instances:    {stat key: [instance names]}: a request for the key also returns one stat per instance, such as
                  net:vmnic0|speed for net|speed, as VCF Operations does.
    Every stat has the value 1.0, one sample per 5-minute cycle: the latest now, or the history over the window asked.
    """

    def __init__(self, resources, files=None, old_keys=(), instances=None):
        self.resources = list(resources)
        self.by_id = {resource.id: resource for resource in self.resources}
        self.files = files or {}
        self.old_keys = tuple(old_keys)
        self.instances = instances or {}

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def query_for_resources(self, query):
        from aria.ops.suite_api_client import SuiteApiClient
        return SuiteApiClient.query_for_resources(self, query)

    def paged_post(self, path, key, json):
        kinds = set(json.get("resourceKind", []))
        adapter_kinds = set(json.get("adapterKind", []))
        return {key: [
            {"identifier": resource.id, "resourceKey": resource.key_json()}
            for resource in self.resources
            if resource.kind in kinds and (not adapter_kinds or resource.adapter_kind in adapter_kinds)
        ]}

    def post(self, path, json):
        if "propertyKeys" in json:
            return FakeResponse({"values": [
                {"resourceId": resource_id, "property-contents": {"property-content": [
                    {"statKey": key, "timestamps": [0], "values": [self._property(resource_id, key)]}
                    for key in json["propertyKeys"]
                ]}}
                for resource_id in json["resourceIds"]
            ]})
        return FakeResponse({"values": [
            {"resourceId": resource_id, "stat-list": {"stat": [
                {"statKey": {"key": full_key}, "timestamps": timestamps, "data": [1.0] * len(timestamps)}
                for key in json["statKey"]
                for full_key in [key] + self._instance_keys(key)
                for timestamps in [self._timestamps(key, json)]
            ]}}
            for resource_id in json["resourceId"]
        ]})

    def get(self, url, **kwargs):
        if url.startswith("api/configurations/files?path=SolutionConfig/"):
            name = url.rsplit("/", 1)[1][:-len(".xml")]
            if name not in self.files:
                return FakeResponse({}, 404)
            return FakeResponse({}, text=self.files[name])
        if url.startswith("api/adapters?adapterKindKey="):
            kind = url.split("=", 1)[1]
            return FakeResponse({"adapterInstancesInfoDto": [
                {"id": resource.id, "resourceKey": resource.key_json()}
                for resource in self.resources if resource.adapter_kind == kind and resource.kind.endswith("Adapter Instance")
            ]})
        if "/relationships?relationshipType=" in url:
            resource_id = url.split("/")[2]
            relation = url.rsplit("=", 1)[1]
            related = self.by_id[resource_id].children if relation == "CHILD" else self.by_id[resource_id].parents
            return FakeResponse({"resourceList": [
                {"resourceKey": {"resourceKindKey": kind}, "links": [{"rel": "SELF", "href": f"/suite-api/api/resources/{rid}"}]}
                for kind, rid in related
            ]})
        raise AssertionError(f"FakeVcfOperations has no answer for GET {url}")

    def _property(self, resource_id, key):
        resource = self.by_id.get(resource_id)
        return resource.properties.get(key, "1") if resource else "1"

    def _instance_keys(self, key):
        group, _, rest = key.partition("|")
        return [f"{group}:{instance}|{rest}" for instance in self.instances.get(key, [])]

    def _timestamps(self, key, json):
        now = time.time() * 1000
        if "begin" in json:
            end = min(json["end"], now)
            count = max(1, int((end - json["begin"]) // CYCLE_MS))
            return [end - (count - 1 - i) * CYCLE_MS for i in range(count)]
        if key.startswith(self.old_keys):
            return [now - 3 * 24 * 3600 * 1000]
        return [now - CYCLE_MS, now]
