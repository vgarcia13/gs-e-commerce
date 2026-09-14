import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

User = get_user_model()

pytestmark = pytest.mark.django_db

SIGNUP_URL = reverse("accounts:signup")
LOGIN_URL = reverse("accounts:login")
LOGOUT_URL = reverse("accounts:logout")
CATALOG_URL = reverse("catalog:product_list")

PASSWORD = "s3cret-pass-99"


def signup_payload(**overrides):
    return {
        "email": "buyer@example.com",
        "password1": PASSWORD,
        "password2": PASSWORD,
        **overrides,
    }


def test_signup_creates_a_customer_and_logs_them_in(client):
    response = client.post(SIGNUP_URL, signup_payload())

    assert response.status_code == 302
    assert response.url == CATALOG_URL
    user = User.objects.get(email="buyer@example.com")
    assert user.is_staff is False
    assert client.session["_auth_user_id"] == str(user.pk)


def test_signup_cannot_grant_staff_or_superuser(client):
    client.post(SIGNUP_URL, signup_payload(is_staff="true", is_superuser="true"))

    user = User.objects.get(email="buyer@example.com")
    assert user.is_staff is False
    assert user.is_superuser is False


def test_signup_rejects_a_weak_password(client):
    client.post(SIGNUP_URL, signup_payload(password1="password", password2="password"))

    assert User.objects.count() == 0


def test_signup_rejects_mismatched_passwords(client):
    client.post(SIGNUP_URL, signup_payload(password2="something-else-99"))

    assert User.objects.count() == 0


def test_signup_rejects_a_duplicate_email_differing_only_by_case(client):
    User.objects.create_user(email="buyer@example.com", password=PASSWORD)

    client.post(SIGNUP_URL, signup_payload(email="BUYER@example.com"))

    assert User.objects.count() == 1


def test_signup_redirects_authenticated_users_away(client):
    User.objects.create_user(email="buyer@example.com", password=PASSWORD)
    client.login(email="buyer@example.com", password=PASSWORD)

    response = client.get(SIGNUP_URL)

    assert response.status_code == 302


def test_login_accepts_a_differently_cased_email(client):
    User.objects.create_user(email="buyer@example.com", password=PASSWORD)

    response = client.post(LOGIN_URL, {"username": "BUYER@Example.com", "password": PASSWORD})

    assert response.status_code == 302
    assert "_auth_user_id" in client.session


def test_login_rejects_a_wrong_password(client):
    User.objects.create_user(email="buyer@example.com", password=PASSWORD)

    client.post(LOGIN_URL, {"username": "buyer@example.com", "password": "wrong-password-99"})

    assert "_auth_user_id" not in client.session


def test_login_honours_the_next_parameter(client):
    User.objects.create_user(email="buyer@example.com", password=PASSWORD)

    response = client.post(
        f"{LOGIN_URL}?next=/products/1/",
        {"username": "buyer@example.com", "password": PASSWORD},
    )

    assert response.url == "/products/1/"


def test_login_refuses_to_redirect_to_another_host(client):
    User.objects.create_user(email="buyer@example.com", password=PASSWORD)

    response = client.post(
        f"{LOGIN_URL}?next=https://evil.example.net/steal",
        {"username": "buyer@example.com", "password": PASSWORD},
    )

    assert response.url == CATALOG_URL


def test_logout_requires_post(client):
    User.objects.create_user(email="buyer@example.com", password=PASSWORD)
    client.login(email="buyer@example.com", password=PASSWORD)

    assert client.get(LOGOUT_URL).status_code == 405

    response = client.post(LOGOUT_URL)

    assert response.status_code == 302
    assert "_auth_user_id" not in client.session


def test_nav_shows_login_and_signup_when_anonymous(client):
    body = client.get(CATALOG_URL).content.decode()

    assert "Log in" in body
    assert "Sign up" in body
    assert "Log out" not in body


def test_nav_shows_the_user_and_logout_when_authenticated(client):
    User.objects.create_user(email="buyer@example.com", password=PASSWORD)
    client.login(email="buyer@example.com", password=PASSWORD)

    body = client.get(CATALOG_URL).content.decode()

    assert "buyer@example.com" in body
    assert "Log out" in body
    assert f'action="{LOGOUT_URL}"' in body
