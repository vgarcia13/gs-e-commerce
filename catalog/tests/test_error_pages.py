import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

User = get_user_model()

pytestmark = pytest.mark.django_db

PASSWORD = "s3cret-pass-99"


def test_unknown_url_renders_the_custom_404_page(client):
    response = client.get("/no-such-page/")

    assert response.status_code == 404
    body = response.content.decode()
    assert "Page not found" in body
    assert "Back to products" in body


def test_missing_product_renders_the_custom_404_page(client):
    response = client.get("/products/999999/")

    assert response.status_code == 404
    assert "Page not found" in response.content.decode()


@pytest.mark.urls("catalog.tests.error_urls")
def test_permission_denied_still_returns_403_with_a_styled_page(client):
    response = client.get("/raise-403/")

    assert response.status_code == 403
    assert "Not allowed" in response.content.decode()


@pytest.mark.urls("catalog.tests.error_urls")
def test_server_error_returns_500_and_does_not_redirect(client):
    client.raise_request_exception = False

    response = client.get("/raise-500/")

    assert response.status_code == 500
    assert "Server error" in response.content.decode()


@pytest.mark.urls("catalog.tests.error_urls")
def test_server_error_page_has_no_external_dependencies(client):
    client.raise_request_exception = False

    body = client.get("/raise-500/").content.decode()

    assert "site.css" not in body
    assert "Search products" not in body
    assert "Log in" not in body


def test_csrf_failure_returns_403_rather_than_redirecting():
    User.objects.create_user(email="buyer@example.com", password=PASSWORD)
    csrf_client = Client(enforce_csrf_checks=True)

    response = csrf_client.post(
        reverse("accounts:login"), {"username": "buyer@example.com", "password": PASSWORD}
    )

    assert response.status_code == 403
    assert "Form expired" in response.content.decode()
