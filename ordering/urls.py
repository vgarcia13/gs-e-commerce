from django.urls import path

from ordering import views

app_name = "ordering"

urlpatterns = [
    path("", views.CartView.as_view(), name="cart"),
    path("add/<int:pk>/", views.AddToCartView.as_view(), name="add"),
    path("update/<int:pk>/", views.UpdateCartItemView.as_view(), name="update"),
    path("remove/<int:pk>/", views.RemoveCartItemView.as_view(), name="remove"),
]
