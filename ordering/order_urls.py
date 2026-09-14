from django.urls import path

from ordering import views

app_name = "orders"

urlpatterns = [
    path("", views.OrderListView.as_view(), name="order_list"),
    path("<str:reference>/", views.OrderDetailView.as_view(), name="order_detail"),
]
