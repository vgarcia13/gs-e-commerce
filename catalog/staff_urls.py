from django.urls import path

from catalog import staff_views

app_name = "catalog_staff"

urlpatterns = [
    path("", staff_views.StaffProductListView.as_view(), name="product_list"),
    path("new/", staff_views.StaffProductCreateView.as_view(), name="product_create"),
    path("<int:pk>/edit/", staff_views.StaffProductUpdateView.as_view(), name="product_update"),
    path("<int:pk>/delete/", staff_views.StaffProductDeleteView.as_view(), name="product_delete"),
    path("<int:pk>/restore/", staff_views.StaffProductRestoreView.as_view(), name="product_restore"),
    path("<int:pk>/stock/", staff_views.StaffStockAdjustView.as_view(), name="stock_adjust"),
]
