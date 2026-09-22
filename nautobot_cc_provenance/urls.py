"""Django urlpatterns declaration for nautobot_cc_provenance app."""

from django.templatetags.static import static
from django.urls import path
from django.views.generic import RedirectView
from nautobot.apps.urls import NautobotUIViewSetRouter

from nautobot_cc_provenance import views

app_name = "nautobot_cc_provenance"
router = NautobotUIViewSetRouter()

urlpatterns = [
    path(
        "device/<uuid:pk>/config-context-provenance/",
        views.DeviceConfigContextProvenanceView.as_view(),
        name="device_config_context_provenance",
    ),
    path(
        "virtual-machine/<uuid:pk>/config-context-provenance/",
        views.VirtualMachineConfigContextProvenanceView.as_view(),
        name="virtualmachine_config_context_provenance",
    ),
    path("docs/", RedirectView.as_view(url=static("nautobot_cc_provenance/docs/index.html")), name="docs"),
]

urlpatterns += router.urls
