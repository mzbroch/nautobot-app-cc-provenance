"""Tests for config context provenance."""

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import SimpleTestCase
from django.urls import reverse
from nautobot.apps.testing import TestCase
from nautobot.core.testing.api import APITestCase
from nautobot.dcim.models import Device, DeviceType, Location, LocationType, Manufacturer
from nautobot.extras.models import ConfigContext, Role, Status
from rest_framework import status

from nautobot_cc_provenance import provenance


def _source(name, weight=None, kind=provenance.SOURCE_CONFIG_CONTEXT):
    """Build a provenance source for the pure merge tests."""
    return provenance.ProvenanceSource(kind=kind, name=name, weight=weight)


def _layer(name, weight, data, kind=provenance.SOURCE_CONFIG_CONTEXT):
    """Build a provenance layer for the pure merge tests."""
    return provenance.ProvenanceLayer(source=_source(name, weight, kind), data=data)


def create_device_environment():
    """Create the minimum Nautobot objects needed to own a config context."""
    manufacturer, _ = Manufacturer.objects.get_or_create(name="CCP Test Networks")
    site_type, _ = LocationType.objects.get_or_create(name="CCP Test Site Type")
    site_type.content_types.add(ContentType.objects.get_for_model(Device))
    location_status = Status.objects.get_for_model(Location).first()
    device_status = Status.objects.get_for_model(Device).first()
    site, _ = Location.objects.get_or_create(
        name="CCP Test Site",
        location_type=site_type,
        status=location_status,
    )
    device_type, _ = DeviceType.objects.get_or_create(
        manufacturer=manufacturer,
        model="CCP-TEST-1000",
    )
    device_role, _ = Role.objects.get_or_create(name="CCP Test Leaf", color="ff0000")
    device_role.content_types.add(ContentType.objects.get_for_model(Device))
    device, _ = Device.objects.get_or_create(
        device_type=device_type,
        role=device_role,
        name="ccp-test-leaf01",
        location=site,
        status=device_status,
    )
    return device


class MergeWithProvenanceTest(SimpleTestCase):
    """The merge replay itself, with no database involved."""

    def _records(self, layers):
        """Return the records keyed by path for the given layers."""
        _, records = provenance.merge_with_provenance(layers)
        return records

    def test_last_layer_applied_wins(self):
        """The layer applied last owns the path, because weight order is ascending."""
        records = self._records(
            [
                _layer("Global Defaults", 1000, {"intended-firmware": {"version": "5.9.2"}}),
                _layer("Platform Baseline", 1500, {"intended-firmware": {"version": "5.11.0"}}),
            ]
        )

        record = records["intended-firmware.version"]
        self.assertEqual(record.value, "5.11.0")
        self.assertEqual(record.source.name, "Platform Baseline")
        self.assertEqual(record.source.weight, 1500)

    def test_shadowed_entries_are_recorded_newest_first(self):
        """Every overwritten value is kept, most recently shadowed first."""
        records = self._records(
            [
                _layer("A", 1000, {"key": "first"}),
                _layer("B", 1200, {"key": "second"}),
                _layer("C", 1400, {"key": "third"}),
            ]
        )

        record = records["key"]
        self.assertEqual(record.value, "third")
        self.assertTrue(record.is_conflicted)
        self.assertEqual([entry.value for entry in record.shadowed], ["second", "first"])
        self.assertEqual([entry.source.name for entry in record.shadowed], ["B", "A"])

    def test_non_overlapping_paths_are_not_conflicted(self):
        """A context that applies but writes nothing at a path is not a source."""
        records = self._records(
            [
                _layer("A", 1000, {"alpha": 1}),
                _layer("B", 1200, {"beta": 2}),
            ]
        )

        self.assertFalse(records["alpha"].is_conflicted)
        self.assertFalse(records["beta"].is_conflicted)
        self.assertEqual(records["beta"].source.name, "B")

    def test_dicts_merge_recursively(self):
        """Sibling keys from different layers coexist under the same parent."""
        merged, records = provenance.merge_with_provenance(
            [
                _layer("A", 1000, {"ztp": {"ipv4": ["10.0.0.1"], "retries": 3}}),
                _layer("B", 1200, {"ztp": {"retries": 5}}),
            ]
        )

        self.assertEqual(merged, {"ztp": {"ipv4": ["10.0.0.1"], "retries": 5}})
        self.assertEqual(records["ztp.ipv4"].source.name, "A")
        self.assertEqual(records["ztp.retries"].source.name, "B")

    def test_lists_are_replaced_wholesale(self):
        """A list is one leaf with one source; elements are never merged."""
        merged, records = provenance.merge_with_provenance(
            [
                _layer("A", 1000, {"skip": ["bios", "cpld"]}),
                _layer("B", 1200, {"skip": ["bios"]}),
            ]
        )

        self.assertEqual(merged["skip"], ["bios"])
        record = records["skip"]
        self.assertTrue(record.is_list)
        self.assertEqual(record.source.name, "B")
        self.assertEqual(record.shadowed[0].value, ["bios", "cpld"])

    def test_subtree_replaced_by_scalar_collapses_descendants(self):
        """Descendant records become shadowed entries of the replacing scalar."""
        merged, records = provenance.merge_with_provenance(
            [
                _layer("A", 1000, {"cfg": {"a": 1, "b": 2}}),
                _layer("B", 1200, {"cfg": "disabled"}),
            ]
        )

        self.assertEqual(merged, {"cfg": "disabled"})
        self.assertNotIn("cfg.a", records)
        self.assertNotIn("cfg.b", records)

        record = records["cfg"]
        self.assertEqual(record.source.name, "B")
        self.assertEqual(
            sorted((entry.path, entry.value) for entry in record.shadowed),
            [("cfg.a", 1), ("cfg.b", 2)],
        )

    def test_scalar_replaced_by_subtree_is_carried_to_leaves(self):
        """A scalar buried by a nested structure is still reported, at its own path."""
        merged, records = provenance.merge_with_provenance(
            [
                _layer("A", 1000, {"cfg": "disabled"}),
                _layer("B", 1200, {"cfg": {"a": 1}}),
            ]
        )

        self.assertEqual(merged, {"cfg": {"a": 1}})
        record = records["cfg.a"]
        self.assertEqual(record.source.name, "B")
        self.assertEqual(record.shadowed[0].path, "cfg")
        self.assertEqual(record.shadowed[0].value, "disabled")
        self.assertEqual(record.shadowed[0].source.name, "A")

    def test_local_data_applied_last_wins(self):
        """Local config context data outranks every config context."""
        records = self._records(
            [
                _layer("Highest Weight", 9000, {"key": "from-context"}),
                _layer(
                    provenance.LOCAL_LABEL,
                    None,
                    {"key": "from-local"},
                    kind=provenance.SOURCE_LOCAL,
                ),
            ]
        )

        record = records["key"]
        self.assertEqual(record.value, "from-local")
        self.assertTrue(record.source.is_local)
        self.assertIsNone(record.source.weight)

    def test_null_value_is_a_real_value(self):
        """An explicit null overwrites, and is distinguished from an absent key."""
        merged, records = provenance.merge_with_provenance(
            [
                _layer("A", 1000, {"key": "value"}),
                _layer("B", 1200, {"key": None}),
            ]
        )

        self.assertEqual(merged, {"key": None})
        self.assertEqual(records["key"].source.name, "B")
        self.assertEqual(records["key"].shadowed[0].value, "value")

    def test_layer_data_is_not_mutated(self):
        """The merge never writes back into the source context data."""
        source_data = {"nested": {"key": "original"}}
        provenance.merge_with_provenance(
            [
                _layer("A", 1000, source_data),
                _layer("B", 1200, {"nested": {"key": "replacement"}}),
            ]
        )

        self.assertEqual(source_data, {"nested": {"key": "original"}})


class DivergingPathsTest(SimpleTestCase):
    """The parity comparison used to decide whether attribution is trustworthy."""

    def test_identical_structures_do_not_diverge(self):
        """Equal dictionaries produce no diverging paths."""
        payload = {"a": {"b": [1, 2]}, "c": None}
        self.assertEqual(provenance.diverging_paths(payload, dict(payload)), [])

    def test_missing_key_diverges(self):
        """A key present on only one side is reported."""
        self.assertEqual(provenance.diverging_paths({"a": 1}, {"a": 1, "b": 2}), ["b"])

    def test_differing_leaf_diverges_at_its_path(self):
        """A differing leaf is reported at its full dotted path."""
        self.assertEqual(
            provenance.diverging_paths({"a": {"b": 1}}, {"a": {"b": 2}}),
            ["a.b"],
        )


class FilterRecordsTest(SimpleTestCase):
    """The view-level filters over a built record list."""

    def setUp(self):
        """Build a small record list covering both filters."""
        self.conflicted = provenance.ProvenanceRecord(
            path="intended-firmware.version",
            value="5.11.0",
            source=_source("Platform Baseline", 1500),
            shadowed=[
                provenance.ShadowedValue(
                    path="intended-firmware.version",
                    value="5.9.2",
                    source=_source("Global Defaults", 1000),
                )
            ],
        )
        self.clean = provenance.ProvenanceRecord(
            path="ztp.retries",
            value=3,
            source=_source("Global Defaults", 1000),
        )
        self.records = [self.conflicted, self.clean]

    def test_conflicts_only_keeps_shadowed_paths(self):
        """The conflicts filter drops paths with a single source."""
        filtered = provenance.filter_records(self.records, conflicts_only=True)
        self.assertEqual(filtered, [self.conflicted])

    def test_query_matches_path_case_insensitively(self):
        """The search filter matches on the dotted path, ignoring case."""
        filtered = provenance.filter_records(self.records, query="ZTP")
        self.assertEqual(filtered, [self.clean])

    def test_filters_combine(self):
        """Both filters apply together."""
        self.assertEqual(
            provenance.filter_records(self.records, conflicts_only=True, query="ztp"),
            [],
        )


class BuildProvenanceTest(TestCase):
    """Resolution against real config contexts, including the parity guarantee."""

    @classmethod
    def setUpTestData(cls):  # pylint: disable=invalid-name
        """Create a device and the config contexts that apply to it."""
        cls.device = create_device_environment()

    def setUp(self):
        """Start each test from a clean set of config contexts."""
        ConfigContext.objects.all().delete()

    def test_layers_are_ordered_by_weight_then_name(self):
        """Layers arrive in the order Nautobot applies them."""
        ConfigContext.objects.create(name="zulu", weight=1000, data={"k": 1})
        ConfigContext.objects.create(name="alpha", weight=1000, data={"k": 2})
        ConfigContext.objects.create(name="middle", weight=500, data={"k": 3})

        layers = provenance.config_context_layers(self.device)

        self.assertEqual([layer.source.name for layer in layers], ["middle", "alpha", "zulu"])

    def test_replay_matches_nautobots_own_merge(self):
        """The reconstruction reproduces get_config_context() exactly."""
        ConfigContext.objects.create(
            name="Global Defaults",
            weight=1000,
            data={"intended-firmware": {"version": "5.9.2"}, "ztp": {"retries": 3}},
        )
        ConfigContext.objects.create(
            name="Platform Baseline",
            weight=1500,
            data={"intended-firmware": {"version": "5.11.0"}},
        )

        result = provenance.build_provenance(self.device)

        self.assertEqual(result.parity, provenance.PARITY_OK)
        self.assertEqual(result.diverging_paths, [])
        self.assertEqual(result.merged, self.device.get_config_context())
        self.assertTrue(result.is_trustworthy)

    def test_attribution_names_the_winning_context(self):
        """The record for a contested path names the highest-weight context."""
        ConfigContext.objects.create(
            name="Global Defaults",
            weight=1000,
            data={"intended-firmware": {"version": "5.9.2"}},
        )
        ConfigContext.objects.create(
            name="Platform Baseline",
            weight=1500,
            data={"intended-firmware": {"version": "5.11.0"}},
        )

        result = provenance.build_provenance(self.device)
        record = next(r for r in result.records if r.path == "intended-firmware.version")

        self.assertEqual(record.value, "5.11.0")
        self.assertEqual(record.source.name, "Platform Baseline")
        self.assertEqual(record.shadowed[0].source.name, "Global Defaults")
        self.assertEqual(result.conflict_count, 1)
        self.assertEqual(result.candidate_contexts, 2)

    def test_local_context_data_is_attributed_and_wins(self):
        """Local data is reported as its own source and outranks contexts."""
        ConfigContext.objects.create(name="Global Defaults", weight=9000, data={"key": "context"})
        self.device.local_config_context_data = {"key": "local"}
        self.device.save()

        result = provenance.build_provenance(self.device)
        record = next(r for r in result.records if r.path == "key")

        self.assertEqual(record.value, "local")
        self.assertTrue(record.source.is_local)
        self.assertTrue(result.has_local_data)
        self.assertEqual(result.candidate_contexts, 1)

    def test_records_are_sorted_by_path(self):
        """Records come back in a stable, readable order."""
        ConfigContext.objects.create(
            name="Global Defaults",
            weight=1000,
            data={"zebra": 1, "alpha": 2, "middle": {"nested": 3}},
        )

        result = provenance.build_provenance(self.device)

        self.assertEqual(
            [record.path for record in result.records],
            ["alpha", "middle.nested", "zebra"],
        )

    def test_no_applicable_context_yields_no_records(self):
        """An object with no config context produces an empty, trustworthy result."""
        result = provenance.build_provenance(self.device)

        self.assertEqual(result.records, [])
        self.assertEqual(result.parity, provenance.PARITY_OK)
        self.assertEqual(result.candidate_contexts, 0)

    def test_contexts_the_user_cannot_view_are_redacted_not_hidden(self):
        """A restricted source keeps its weight and loses its identity."""
        ConfigContext.objects.create(name="Secret Baseline", weight=1500, data={"key": "value"})
        limited_user = get_user_model().objects.create_user(username="limited")

        layers = provenance.config_context_layers(self.device, user=limited_user)

        self.assertEqual(len(layers), 1)
        source = layers[0].source
        self.assertTrue(source.restricted)
        self.assertEqual(source.name, provenance.RESTRICTED_LABEL)
        self.assertEqual(source.weight, 1500)
        self.assertIsNone(source.context_id)

    def test_contexts_the_user_can_view_are_named(self):
        """A superuser sees every context by name."""
        ConfigContext.objects.create(name="Visible Baseline", weight=1500, data={"key": "value"})
        admin = get_user_model().objects.create_superuser(username="admin-provenance")

        layers = provenance.config_context_layers(self.device, user=admin)

        self.assertEqual(layers[0].source.name, "Visible Baseline")
        self.assertFalse(layers[0].source.restricted)

    def test_parity_can_be_skipped(self):
        """Skipping the check is reported, not silently presented as verified."""
        ConfigContext.objects.create(name="Global Defaults", weight=1000, data={"key": "value"})

        result = provenance.build_provenance(self.device, check_parity=False)

        self.assertEqual(result.parity, provenance.PARITY_SKIPPED)
        self.assertTrue(result.is_trustworthy)


class ProvenanceAPITest(APITestCase):
    """The read-only REST surface."""

    @classmethod
    def setUpTestData(cls):  # pylint: disable=invalid-name
        """Create a device with two overlapping config contexts."""
        cls.device = create_device_environment()
        ConfigContext.objects.create(
            name="Global Defaults",
            weight=1000,
            data={"intended-firmware": {"version": "5.9.2"}, "ztp": {"retries": 3}},
        )
        ConfigContext.objects.create(
            name="Platform Baseline",
            weight=1500,
            data={"intended-firmware": {"version": "5.11.0"}},
        )

    def setUp(self):
        super().setUp()
        self.url = reverse(
            "plugins-api:nautobot_cc_provenance-api:device_config_context_provenance",
            kwargs={"pk": self.device.pk},
        )

    def test_requires_view_permission_on_the_object(self):
        """Without device view permission the object is not found."""
        response = self.client.get(self.url, **self.header)
        self.assertIn(
            response.status_code,
            (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND),
        )

    def test_returns_provenance_for_every_path(self):
        """A permitted read returns one record per leaf path, with sources."""
        self.add_permissions("dcim.view_device")

        response = self.client.get(self.url, **self.header)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["parity"], provenance.PARITY_OK)
        self.assertEqual(response.data["candidate_contexts"], 2)
        self.assertEqual(response.data["object"]["id"], str(self.device.pk))

        paths = {entry["path"]: entry for entry in response.data["paths"]}
        self.assertEqual(
            sorted(paths),
            ["intended-firmware.version", "ztp.retries"],
        )
        self.assertEqual(
            paths["intended-firmware.version"]["source"]["name"],
            "Platform Baseline",
        )
        self.assertEqual(
            paths["intended-firmware.version"]["shadowed"][0]["source"]["name"],
            "Global Defaults",
        )

    def test_conflicts_only_narrows_the_payload(self):
        """The conflicts filter returns only contested paths."""
        self.add_permissions("dcim.view_device")

        response = self.client.get(f"{self.url}?conflicts_only=true", **self.header)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [entry["path"] for entry in response.data["paths"]],
            ["intended-firmware.version"],
        )
        self.assertEqual(response.data["conflict_count"], 1)

    def test_unknown_object_is_not_found(self):
        """An unknown primary key returns 404 rather than an empty result."""
        self.add_permissions("dcim.view_device")
        url = reverse(
            "plugins-api:nautobot_cc_provenance-api:device_config_context_provenance",
            kwargs={"pk": "00000000-0000-0000-0000-000000000000"},
        )

        response = self.client.get(url, **self.header)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
