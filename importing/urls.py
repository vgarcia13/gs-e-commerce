from django.urls import path

from importing import views

app_name = "importing"

urlpatterns = [
    path("", views.CsvImportView.as_view(), name="csv_import"),
]
