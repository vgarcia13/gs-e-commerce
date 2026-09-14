import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError

User = get_user_model()

pytestmark = pytest.mark.django_db


def test_create_user_is_not_staff_by_default():
    user = User.objects.create_user(email="buyer@example.com", password="s3cret-pass-99")

    assert user.is_staff is False
    assert user.is_superuser is False
    assert user.check_password("s3cret-pass-99")


def test_create_superuser_is_staff_and_superuser():
    user = User.objects.create_superuser(email="boss@example.com", password="s3cret-pass-99")

    assert user.is_staff is True
    assert user.is_superuser is True


def test_email_is_lowercased_on_save():
    user = User.objects.create_user(email="  Buyer@Example.COM ", password="s3cret-pass-99")

    assert user.email == "buyer@example.com"


def test_email_must_be_unique_regardless_of_case():
    User.objects.create_user(email="buyer@example.com", password="s3cret-pass-99")

    with pytest.raises(IntegrityError):
        User.objects.create_user(email="BUYER@EXAMPLE.COM", password="s3cret-pass-99")


def test_email_is_required():
    with pytest.raises(ValueError):
        User.objects.create_user(email="", password="s3cret-pass-99")


def test_superuser_cannot_be_created_without_staff_flag():
    with pytest.raises(ValueError):
        User.objects.create_superuser(
            email="boss@example.com", password="s3cret-pass-99", is_staff=False
        )


def test_username_field_is_email():
    assert User.USERNAME_FIELD == "email"
    assert User.REQUIRED_FIELDS == []


def test_user_has_no_username_field():
    assert "username" not in {field.name for field in User._meta.get_fields()}


def test_str_is_the_email():
    user = User.objects.create_user(email="buyer@example.com", password="s3cret-pass-99")

    assert str(user) == "buyer@example.com"


def test_project_settings_do_not_weaken_password_hashing():
    import config.settings as project_settings

    assert not hasattr(project_settings, "PASSWORD_HASHERS")
