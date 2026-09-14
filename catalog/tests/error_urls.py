from django.core.exceptions import PermissionDenied
from django.urls import path

from config.urls import urlpatterns as project_urlpatterns


def raise_permission_denied(request):
    raise PermissionDenied


def raise_server_error(request):
    raise RuntimeError("deliberate failure")


urlpatterns = [
    path("raise-403/", raise_permission_denied),
    path("raise-500/", raise_server_error),
    *project_urlpatterns,
]
