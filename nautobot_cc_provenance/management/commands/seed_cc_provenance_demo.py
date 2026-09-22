"""Seed demonstration data for config context provenance.

Every object this command creates is named with a `CCP` prefix, so `--flush`
removes exactly what was seeded and nothing else.

Config contexts are scoped to the demo sites, roles, platforms and tenant rather
than left global, so seeding does not change the config context of any device
that already exists in the instance.
"""

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db import transaction
from django.urls import reverse
from nautobot.dcim.models import Device, DeviceType, Location, LocationType, Manufacturer, Platform
from nautobot.extras.models import ConfigContext, Role, Status
from nautobot.tenancy.models import Tenant

REGION_TYPE = "CCP Region"
SITE_TYPE = "CCP Site"

REGIONS = ["CCP-EMEA", "CCP-AMER"]
SITES = {
    "ccp-ams01": "CCP-EMEA",
    "ccp-fra01": "CCP-EMEA",
    "ccp-dfw01": "CCP-AMER",
}

MANUFACTURER = "CCP Networks"
DEVICE_TYPES = ["CCP-SN5600", "CCP-7050CX3"]
PLATFORMS = ["CCP Cumulus Linux", "CCP Arista EOS"]
ROLES = ["CCP Leaf", "CCP Spine"]
TENANT = "CCP Fabric Prod"

DEVICES = [
    {
        "name": "ccp-ams01-leaf01",
        "site": "ccp-ams01",
        "role": "CCP Leaf",
        "platform": "CCP Cumulus Linux",
        "device_type": "CCP-SN5600",
        "tenant": TENANT,
        "local_config_context_data": {"intended-firmware": {"version": "5.12.0-local"}},
    },
    {
        "name": "ccp-ams01-spine01",
        "site": "ccp-ams01",
        "role": "CCP Spine",
        "platform": "CCP Cumulus Linux",
        "device_type": "CCP-SN5600",
        "tenant": None,
        "local_config_context_data": None,
    },
    {
        "name": "ccp-fra01-leaf01",
        "site": "ccp-fra01",
        "role": "CCP Leaf",
        "platform": "CCP Arista EOS",
        "device_type": "CCP-7050CX3",
        "tenant": TENANT,
        "local_config_context_data": None,
    },
    {
        "name": "ccp-dfw01-leaf01",
        "site": "ccp-dfw01",
        "role": "CCP Leaf",
        "platform": "CCP Cumulus Linux",
        "device_type": "CCP-SN5600",
        "tenant": None,
        "local_config_context_data": None,
    },
    {
        "name": "ccp-dfw01-spine01",
        "site": "ccp-dfw01",
        "role": "CCP Spine",
        "platform": "CCP Arista EOS",
        "device_type": "CCP-7050CX3",
        "tenant": None,
        "local_config_context_data": None,
    },
]

CONFIG_CONTEXTS = [
    {
        "name": "CCP Global Defaults",
        "weight": 1000,
        "scope": {"locations": list(SITES)},
        "data": {
            "intended-firmware": {"version": "5.9.2"},
            "ntp": {"servers": ["10.0.0.1", "10.0.0.2"]},
            "dns": {"servers": ["10.0.0.53"]},
            "snmp": {"community": "public"},
        },
    },
    {
        "name": "CCP Region EMEA",
        "weight": 1200,
        "scope": {"locations": ["ccp-ams01", "ccp-fra01"]},
        "data": {
            "ntp": {"servers": ["10.1.0.1"]},
            "timezone": "Europe/Amsterdam",
        },
    },
    {
        "name": "CCP Site AMS01",
        "weight": 1300,
        "scope": {"locations": ["ccp-ams01"]},
        "data": {
            "syslog": {"host": "10.1.1.10"},
            "dns": {"servers": ["10.1.1.53", "10.1.1.54"]},
        },
    },
    {
        "name": "CCP Role Leaf",
        "weight": 1400,
        "scope": {"roles": ["CCP Leaf"]},
        "data": {
            "intended-firmware": {"version": "5.10.1"},
            "bgp": {"asn_base": 65100},
        },
    },
    {
        "name": "CCP Platform Cumulus",
        "weight": 1500,
        "scope": {"platforms": ["CCP Cumulus Linux"]},
        "data": {
            "intended-firmware": {"version": "5.11.0"},
            "features": {"evpn": True},
        },
    },
    {
        "name": "CCP Tenant Fabric Prod",
        "weight": 1600,
        "scope": {"tenants": [TENANT]},
        "data": {
            "snmp": {"community": "fabric-prod-ro"},
            "features": {"telemetry": True},
        },
    },
    {
        "name": "CCP Tiebreak AAA",
        "weight": 1700,
        "scope": {"locations": list(SITES)},
        "data": {"tiebreak": {"winner": "aaa"}},
    },
    {
        "name": "CCP Tiebreak ZZZ",
        "weight": 1700,
        "scope": {"locations": list(SITES)},
        "data": {"tiebreak": {"winner": "zzz"}},
    },
    {
        "name": "CCP Spine Feature Override",
        "weight": 1800,
        "scope": {"roles": ["CCP Spine"]},
        "data": {"features": "disabled"},
    },
]

WHAT_TO_LOOK_AT = [
    (
        "ccp-ams01-leaf01",
        "intended-firmware.version resolves to 5.12.0-local with 3 shadowed values. "
        "Local data outranks every context, including the highest weight.",
    ),
    (
        "ccp-ams01-spine01",
        'features resolves to the scalar "disabled", collapsing features.evpn into '
        "its shadowed list. A scalar replaces a whole subtree.",
    ),
    (
        "ccp-fra01-leaf01",
        "dns.servers and ntp.servers are single paths labelled list. Deep merge "
        "replaces a list wholesale rather than merging elements.",
    ),
    (
        "ccp-dfw01-leaf01",
        "tiebreak.winner resolves to zzz. Two contexts share weight 1700, so the "
        "tie breaks on name ascending and the later name is applied last.",
    ),
]


class Command(BaseCommand):
    """Seed locations, devices and layered config contexts that demonstrate provenance."""

    help = "Seed demo data demonstrating config context provenance."

    def add_arguments(self, parser):
        """Register the command's options."""
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Delete previously seeded CCP demo objects instead of creating them.",
        )

    def handle(self, *args, **options):
        """Create, or with --flush remove, the demo data."""
        if options["flush"]:
            self._flush()
            return

        with transaction.atomic():
            self._seed()

    def _flush(self):
        """Remove every object this command creates, in dependency order."""
        counts = {
            "devices": Device.objects.filter(name__in=[entry["name"] for entry in DEVICES]).delete(),
            "config contexts": ConfigContext.objects.filter(
                name__in=[entry["name"] for entry in CONFIG_CONTEXTS]
            ).delete(),
            "tenants": Tenant.objects.filter(name=TENANT).delete(),
            "platforms": Platform.objects.filter(name__in=PLATFORMS).delete(),
            "device types": DeviceType.objects.filter(model__in=DEVICE_TYPES).delete(),
            "manufacturers": Manufacturer.objects.filter(name=MANUFACTURER).delete(),
            "roles": Role.objects.filter(name__in=ROLES).delete(),
            "locations": Location.objects.filter(name__in=list(SITES)).delete(),
            "regions": Location.objects.filter(name__in=REGIONS).delete(),
            "location types": LocationType.objects.filter(name__in=[SITE_TYPE, REGION_TYPE]).delete(),
        }

        for label, (deleted, _) in counts.items():
            self.stdout.write(f"  removed {deleted} {label}")
        self.stdout.write(self.style.SUCCESS("CCP demo data flushed."))

    def _seed(self):  # pylint: disable=too-many-locals
        """Create the demo objects and report what to look at."""
        device_ct = ContentType.objects.get_for_model(Device)
        location_status = Status.objects.get_for_model(Location).get(name="Active")
        device_status = Status.objects.get_for_model(Device).get(name="Active")

        region_type = self._ensure(LocationType, name=REGION_TYPE, defaults={"nestable": True})
        site_type = self._ensure(LocationType, name=SITE_TYPE, defaults={"parent": region_type})
        site_type.content_types.add(device_ct)

        regions = {
            name: self._ensure(
                Location,
                name=name,
                defaults={"location_type": region_type, "status": location_status},
            )
            for name in REGIONS
        }
        sites = {
            name: self._ensure(
                Location,
                name=name,
                defaults={
                    "location_type": site_type,
                    "status": location_status,
                    "parent": regions[parent],
                },
            )
            for name, parent in SITES.items()
        }

        manufacturer = self._ensure(Manufacturer, name=MANUFACTURER)
        device_types = {
            model: self._ensure(DeviceType, model=model, defaults={"manufacturer": manufacturer})
            for model in DEVICE_TYPES
        }
        platforms = {
            name: self._ensure(Platform, name=name, defaults={"manufacturer": manufacturer}) for name in PLATFORMS
        }

        roles = {}
        for name in ROLES:
            role = self._ensure(Role, name=name, defaults={"color": "0f7c80"})
            role.content_types.add(device_ct)
            roles[name] = role

        tenant = self._ensure(Tenant, name=TENANT)

        devices = {}
        for entry in DEVICES:
            device = self._ensure(
                Device,
                name=entry["name"],
                defaults={
                    "location": sites[entry["site"]],
                    "role": roles[entry["role"]],
                    "device_type": device_types[entry["device_type"]],
                    "platform": platforms[entry["platform"]],
                    "status": device_status,
                    "tenant": tenant if entry["tenant"] else None,
                },
            )
            if entry["local_config_context_data"] and not device.local_config_context_data:
                device.local_config_context_data = entry["local_config_context_data"]
                device.validated_save()
            devices[entry["name"]] = device

        scope_sources = {
            "locations": sites,
            "roles": roles,
            "platforms": platforms,
            "tenants": {TENANT: tenant},
        }
        for entry in CONFIG_CONTEXTS:
            context = self._ensure(
                ConfigContext,
                name=entry["name"],
                defaults={"weight": entry["weight"], "data": entry["data"]},
            )
            for field, keys in entry["scope"].items():
                getattr(context, field).set([scope_sources[field][key] for key in keys])

        self._report(devices)

    def _ensure(self, model, defaults=None, **lookup):
        """Return the existing object matching `lookup`, or create it with `defaults`."""
        existing = model.objects.filter(**lookup).first()
        if existing is not None:
            return existing

        obj = model(**lookup, **(defaults or {}))
        obj.validated_save()
        self.stdout.write(f"  created {model._meta.verbose_name}: {obj}")
        return obj

    def _report(self, devices):
        """Print what was seeded and which device demonstrates which behaviour."""
        self.stdout.write(self.style.SUCCESS("\nCCP demo data seeded."))
        self.stdout.write(
            f"\n{len(CONFIG_CONTEXTS)} config contexts across weights "
            f"{CONFIG_CONTEXTS[0]['weight']}-{CONFIG_CONTEXTS[-1]['weight']}, "
            f"{len(DEVICES)} devices in {len(SITES)} sites.\n"
        )
        self.stdout.write("Open the Context Provenance tab on each device:\n")

        for name, explanation in WHAT_TO_LOOK_AT:
            url = reverse(
                "plugins:nautobot_cc_provenance:device_config_context_provenance",
                kwargs={"pk": devices[name].pk},
            )
            self.stdout.write(self.style.MIGRATE_HEADING(f"\n  {name}"))
            self.stdout.write(f"    {url}")
            self.stdout.write(f"    {explanation}")

        self.stdout.write("\nRe-run with --flush to remove everything this command created.\n")
