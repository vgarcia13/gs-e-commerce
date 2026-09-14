from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("cart/", include("ordering.urls")),
    path("staff/import/", include("importing.urls")),
    path("staff/products/", include("catalog.staff_urls")),
    path("", include("catalog.urls")),
]
