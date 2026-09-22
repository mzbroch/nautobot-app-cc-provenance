"""Views for the Config Context Provenance tab."""

from nautobot.apps.views import ObjectView
from nautobot.dcim.models import Device
from nautobot.virtualization.models import VirtualMachine

from nautobot_cc_provenance import provenance


class BaseConfigContextProvenanceView(ObjectView):
    """Shared behaviour for the Config Context Provenance detail tab.

    Subclasses supply the queryset of the object type and the detail template
    the tab renders inside.
    """

    template_name = "nautobot_cc_provenance/config_context_provenance_tab.html"
    base_template = ""

    def get_extra_context(self, request, instance=None):
        """Return the provenance records for the object, filtered for display."""
        context = super().get_extra_context(request, instance)

        result = provenance.build_provenance(instance, user=request.user)
        conflicts_only = request.GET.get("conflicts_only") == "true"
        search_query = request.GET.get("q", "")

        context.update(
            {
                "base_template": self.base_template,
                "result": result,
                "records": provenance.filter_records(
                    result.records,
                    conflicts_only=conflicts_only,
                    query=search_query,
                ),
                "conflicts_only": conflicts_only,
                "search_query": search_query,
                "total_paths": len(result.records),
            }
        )
        return context


class DeviceConfigContextProvenanceView(BaseConfigContextProvenanceView):
    """Config Context Provenance tab for `dcim.Device`."""

    queryset = Device.objects.all()
    base_template = "dcim/device.html"


class VirtualMachineConfigContextProvenanceView(BaseConfigContextProvenanceView):
    """Config Context Provenance tab for `virtualization.VirtualMachine`."""

    queryset = VirtualMachine.objects.all()
    base_template = "virtualization/virtualmachine.html"
