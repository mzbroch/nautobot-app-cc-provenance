"""Tests for the seed_cc_provenance_demo management command."""

from io import StringIO

from django.core.management import call_command
from nautobot.apps.testing import TestCase
from nautobot.dcim.models import Device, Location, LocationType, Platform
from nautobot.extras.models import ConfigContext

from nautobot_cc_provenance import provenance


def _record(device, path):
    """Return the provenance record at `path` for `device`."""
    result = provenance.build_provenance(device)
    return result, next((entry for entry in result.records if entry.path == path), None)


class SeedCommandTest(TestCase):
    """The demo data must actually demonstrate what the command claims it does."""

    @classmethod
    def setUpTestData(cls):
        cls.out = StringIO()
        call_command("seed_cc_provenance_demo", stdout=cls.out)

    def test_creates_the_documented_inventory(self):
        self.assertEqual(Location.objects.filter(name__startswith="ccp-").count(), 3)
        self.assertEqual(Location.objects.filter(name__startswith="CCP-").count(), 2)
        self.assertEqual(LocationType.objects.filter(name__startswith="CCP ").count(), 2)
        self.assertEqual(Platform.objects.filter(name__startswith="CCP ").count(), 2)
        self.assertEqual(Device.objects.filter(name__startswith="ccp-").count(), 5)
        self.assertEqual(ConfigContext.objects.filter(name__startswith="CCP ").count(), 9)

    def test_every_seeded_device_replays_cleanly(self):
        for device in Device.objects.filter(name__startswith="ccp-"):
            with self.subTest(device=device.name):
                result = provenance.build_provenance(device)
                self.assertEqual(result.parity, provenance.PARITY_OK)
                self.assertTrue(result.records)

    def test_local_data_beats_every_context(self):
        device = Device.objects.get(name="ccp-ams01-leaf01")
        result, record = _record(device, "intended-firmware.version")

        self.assertEqual(record.value, "5.12.0-local")
        self.assertTrue(record.source.is_local)
        self.assertEqual(
            [entry.value for entry in record.shadowed],
            ["5.11.0", "5.10.1", "5.9.2"],
        )
        self.assertTrue(result.has_local_data)

    def test_equal_weights_break_on_name_ascending(self):
        device = Device.objects.get(name="ccp-dfw01-leaf01")
        _, record = _record(device, "tiebreak.winner")

        self.assertEqual(record.value, "zzz")
        self.assertEqual(record.source.name, "CCP Tiebreak ZZZ")
        self.assertEqual(record.shadowed[0].source.name, "CCP Tiebreak AAA")

    def test_scalar_replaces_a_whole_subtree(self):
        device = Device.objects.get(name="ccp-ams01-spine01")
        _, record = _record(device, "features")

        self.assertEqual(record.value, "disabled")
        self.assertEqual(record.source.name, "CCP Spine Feature Override")
        self.assertIn("features.evpn", [entry.path for entry in record.shadowed])

    def test_lists_are_single_paths(self):
        device = Device.objects.get(name="ccp-fra01-leaf01")
        _, record = _record(device, "ntp.servers")

        self.assertTrue(record.is_list)
        self.assertEqual(record.value, ["10.1.0.1"])
        self.assertEqual(record.shadowed[0].value, ["10.0.0.1", "10.0.0.2"])

    def test_tenant_scoped_context_applies_only_to_its_tenant(self):
        with_tenant = Device.objects.get(name="ccp-ams01-leaf01")
        without_tenant = Device.objects.get(name="ccp-dfw01-spine01")

        _, tenant_record = _record(with_tenant, "snmp.community")
        _, other_record = _record(without_tenant, "snmp.community")

        self.assertEqual(tenant_record.value, "fabric-prod-ro")
        self.assertEqual(other_record.value, "public")

    def test_seeding_twice_is_idempotent(self):
        call_command("seed_cc_provenance_demo", stdout=StringIO())

        self.assertEqual(Device.objects.filter(name__startswith="ccp-").count(), 5)
        self.assertEqual(ConfigContext.objects.filter(name__startswith="CCP ").count(), 9)

    def test_flush_removes_everything_it_created(self):
        call_command("seed_cc_provenance_demo", "--flush", stdout=StringIO())

        self.assertFalse(Device.objects.filter(name__startswith="ccp-").exists())
        self.assertFalse(ConfigContext.objects.filter(name__startswith="CCP ").exists())
        self.assertFalse(LocationType.objects.filter(name__startswith="CCP ").exists())
