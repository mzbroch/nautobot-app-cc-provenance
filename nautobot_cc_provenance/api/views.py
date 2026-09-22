"""REST API views for config context provenance."""

from django.shortcuts import get_object_or_404
from nautobot.dcim.models import Device
from nautobot.virtualization.models import VirtualMachine
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from nautobot_cc_provenance import provenance


class BaseConfigContextProvenanceAPIView(APIView):
    """Explain which config context supplied each key of a merged config context.

    Read-only. The `queryset` attribute names the object type for Nautobot's
    permission machinery; object-level access is enforced by restricting that
    queryset to what the requesting user may view.
    """

    queryset = None

    def get(self, request, pk):
        """Return the provenance of every leaf path in the object's config context."""
        obj = get_object_or_404(self.queryset.restrict(request.user, "view"), pk=pk)
        result = provenance.build_provenance(obj, user=request.user)

        if result.parity == provenance.PARITY_MISMATCH:
            return Response(
                {
                    "parity": result.parity,
                    "diverging_paths": result.diverging_paths,
                    "detail": ("Provenance replay did not reproduce get_config_context(); refusing to attribute."),
                },
                status=status.HTTP_409_CONFLICT,
            )

        payload = result.to_dict()
        payload["object"] = {"id": str(obj.pk), "display": str(obj)}

        if request.query_params.get("conflicts_only") == "true":
            payload["paths"] = [record.to_dict() for record in result.records if record.is_conflicted]

        return Response(payload)


class DeviceConfigContextProvenanceAPIView(BaseConfigContextProvenanceAPIView):
    """Config context provenance for a `dcim.Device`."""

    queryset = Device.objects.all()


class VirtualMachineConfigContextProvenanceAPIView(BaseConfigContextProvenanceAPIView):
    """Config context provenance for a `virtualization.VirtualMachine`."""

    queryset = VirtualMachine.objects.all()
