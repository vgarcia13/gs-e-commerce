import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from catalog.models import Product
from importing.forms import MAX_UPLOAD_BYTES

User = get_user_model()

pytestmark = pytest.mark.django_db

UPLOAD_URL = reverse("importing:csv_import")
CATALOG_URL = reverse("catalog:product_list")
PASSWORD = "s3cret-pass-99"
HEADER = "name,sku,description,category,price,stock,weight_kg\n"


def csv_upload(*rows: str, name: str = "products.csv") -> SimpleUploadedFile:
    content = (HEADER + "".join(row + "\n" for row in rows)).encode("utf-8")
    return SimpleUploadedFile(name, content, content_type="text/csv")


@pytest.fixture
def staff(client):
    user = User.objects.create_user(email="staff@example.com", password=PASSWORD, is_staff=True)
    client.login(email=user.email, password=PASSWORD)
    return user


@pytest.fixture
def customer(client):
    user = User.objects.create_user(email="buyer@example.com", password=PASSWORD)
    client.login(email=user.email, password=PASSWORD)
    return user


def test_anonymous_users_are_redirected_to_login(client):
    response = client.get(UPLOAD_URL)

    assert response.status_code == 302
    assert reverse("accounts:login") in response.url


def test_customers_are_sent_back_with_a_warning(client, customer):
    response = client.get(UPLOAD_URL, follow=True)

    assert response.redirect_chain[-1][0] == CATALOG_URL
    assert "staff only" in response.content.decode()


def test_staff_can_open_the_upload_page(client, staff):
    assert client.get(UPLOAD_URL).status_code == 200


def test_upload_creates_products_and_reports_counts(client, staff):
    response = client.post(
        UPLOAD_URL,
        {"file": csv_upload("Running Shoes,RS-001,Light shoes,Footwear,89.99,150,0.35")},
    )

    assert response.status_code == 200
    assert response.context["report"].created == 1
    assert Product.objects.get(sku="RS-001").stock == 150


def test_upload_reports_rejected_rows_with_line_numbers(client, staff):
    response = client.post(
        UPLOAD_URL,
        {
            "file": csv_upload(
                "Running Shoes,RS-001,Light shoes,Footwear,89.99,150,0.35",
                "Yoga Mat,YM-015,Mat,Sports,free,200,1.2",
            )
        },
    )

    body = response.content.decode()
    assert response.context["report"].created == 1
    assert response.context["report"].rejected == 1
    assert "free" in body
    assert "is not a valid decimal number" in body


def test_upload_reports_superseded_duplicates_as_warnings(client, staff):
    response = client.post(
        UPLOAD_URL,
        {
            "file": csv_upload(
                "Speaker,BS-021,First,Electronics,59.99,110,0.8",
                "Speaker,BS-021,Second,Electronics,49.99,200,0.75",
            )
        },
    )

    assert "BS-021 appears more than once" in response.content.decode()
    assert Product.objects.count() == 1


def test_upload_with_a_missing_column_is_a_form_error(client, staff):
    bad = SimpleUploadedFile(
        "bad.csv",
        b"name,sku,description,category,price,stock\nLamp,DL-007,L,Home,1.00,1\n",
        content_type="text/csv",
    )

    response = client.post(UPLOAD_URL, {"file": bad})

    assert "weight_kg" in response.content.decode()
    assert Product.objects.count() == 0


def test_upload_of_undecodable_bytes_is_a_form_error(client, staff):
    bad = SimpleUploadedFile("bad.csv", b"\xff\xfe\x00name,sku", content_type="text/csv")

    response = client.post(UPLOAD_URL, {"file": bad})

    assert "UTF-8" in response.content.decode()
    assert Product.objects.count() == 0


def test_upload_larger_than_the_limit_is_rejected(client, staff):
    oversized = SimpleUploadedFile(
        "big.csv", b"x" * (MAX_UPLOAD_BYTES + 1), content_type="text/csv"
    )

    response = client.post(UPLOAD_URL, {"file": oversized})

    assert "larger than the 5 MB limit" in response.content.decode()
    assert Product.objects.count() == 0


def test_upload_at_exactly_the_limit_is_accepted(client, staff):
    row = "Running Shoes,RS-001,Light shoes,Footwear,89.99,150,0.35\n"
    padding = b"\n" * (MAX_UPLOAD_BYTES - len(HEADER) - len(row))
    content = HEADER.encode() + row.encode() + padding
    assert len(content) == MAX_UPLOAD_BYTES

    response = client.post(
        UPLOAD_URL, {"file": SimpleUploadedFile("big.csv", content, content_type="text/csv")}
    )

    assert response.context["report"].created == 1


def test_reupload_updates_without_touching_stock(client, staff):
    payload = "Running Shoes,RS-001,Light shoes,Footwear,89.99,150,0.35"
    client.post(UPLOAD_URL, {"file": csv_upload(payload)})
    Product.objects.filter(sku="RS-001").update(stock=7)

    response = client.post(UPLOAD_URL, {"file": csv_upload(payload)})

    assert response.context["report"].updated == 1
    assert response.context["report"].created == 0
    assert Product.objects.get(sku="RS-001").stock == 7


def test_markup_in_the_report_is_escaped(client, staff):
    response = client.post(
        UPLOAD_URL,
        {"file": csv_upload("<script>alert('xss')</script>,XS-001,Normal,Electronics,19.99,x,0.1")},
    )

    body = response.content.decode()
    assert "<script>alert('xss')</script>" not in body
