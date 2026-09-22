"""Template extensions adding the Config Context Provenance tab."""

from django.urls import reverse
from nautobot.apps.ui import TemplateExtension


class DeviceConfigContextProvenanceTab(TemplateExtension):  # pylint: disable=abstract-method
    """Add the Context Provenance tab to `dcim.Device`."""

    model = "dcim.device"

    def detail_tabs(self):
        """Offer the tab on every device, since every device has a config context."""
        return [
            {
                "title": "Context Provenance",
                "url": reverse(
                    "plugins:nautobot_cc_provenance:device_config_context_provenance",
                    kwargs={"pk": self.context["object"].pk},
                ),
            }
        ]


class VirtualMachineConfigContextProvenanceTab(TemplateExtension):  # pylint: disable=abstract-method
    """Add the Context Provenance tab to `virtualization.VirtualMachine`."""

    model = "virtualization.virtualmachine"

    def detail_tabs(self):
        """Offer the tab on every virtual machine."""
        return [
            {
                "title": "Context Provenance",
                "url": reverse(
                    "plugins:nautobot_cc_provenance:virtualmachine_config_context_provenance",
                    kwargs={"pk": self.context["object"].pk},
                ),
            }
        ]


template_extensions = [
    DeviceConfigContextProvenanceTab,
    VirtualMachineConfigContextProvenanceTab,
]
