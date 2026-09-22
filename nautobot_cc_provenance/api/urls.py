"""REST API URLs for nautobot_cc_provenance."""

from django.urls import path

from nautobot_cc_provenance.api import views

app_name = "nautobot_cc_provenance-api"

urlpatterns = [
    path(
        "config-context-provenance/devices/<uuid:pk>/",
        views.DeviceConfigContextProvenanceAPIView.as_view(),
        name="device_config_context_provenance",
    ),
    path(
        "config-context-provenance/virtual-machines/<uuid:pk>/",
        views.VirtualMachineConfigContextProvenanceAPIView.as_view(),
        name="virtualmachine_config_context_provenance",
    ),
]
