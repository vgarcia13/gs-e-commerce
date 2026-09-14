from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from catalog.models import Product

pytestmark = pytest.mark.django_db

HEADER = "name,sku,description,category,price,stock,weight_kg\n"


def write_csv(tmp_path, *rows: str):
    path = tmp_path / "products.csv"
    path.write_text(HEADER + "".join(row + "\n" for row in rows), encoding="utf-8")
    return path


def run(path) -> str:
    out = StringIO()
    call_command("import_products", str(path), stdout=out)
    return out.getvalue()


def test_command_imports_and_reports_counts(tmp_path):
    path = write_csv(tmp_path, "Running Shoes,RS-001,Light shoes,Footwear,89.99,150,0.35")

    output = run(path)

    assert "created 1" in output
    assert Product.objects.count() == 1


def test_command_reports_rejected_rows_with_line_numbers(tmp_path):
    path = write_csv(
        tmp_path,
        "Running Shoes,RS-001,Light shoes,Footwear,89.99,150,0.35",
        "Yoga Mat,YM-015,Mat,Sports,free,200,1.2",
    )

    output = run(path)

    assert "created 1" in output
    assert "rejected: line 3, price" in output
    assert Product.objects.count() == 1


def test_command_reports_superseded_duplicates(tmp_path):
    path = write_csv(
        tmp_path,
        "Speaker,BS-021,First,Electronics,59.99,110,0.8",
        "Speaker,BS-021,Second,Electronics,49.99,200,0.75",
    )

    output = run(path)

    assert "warning: line 3" in output
    assert "BS-021" in output


def test_command_fails_on_missing_required_column(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("name,sku,description,category,price,stock\nLamp,DL-007,L,Home,1.00,1\n")

    with pytest.raises(CommandError, match="weight_kg"):
        call_command("import_products", str(path), stdout=StringIO())


def test_command_fails_on_unreadable_file(tmp_path):
    with pytest.raises(CommandError, match="Cannot read"):
        call_command("import_products", str(tmp_path / "absent.csv"), stdout=StringIO())


def test_command_succeeds_when_only_some_rows_are_rejected(tmp_path):
    path = write_csv(tmp_path, "Yoga Mat,YM-015,Mat,Sports,free,200,1.2")

    output = run(path)

    assert "created 0" in output
    assert "rejected: line 2" in output
