from decimal import Decimal

import pytest

from importing.parser import CsvFormatError, parse

pytestmark = pytest.mark.django_db

HEADER = "name,sku,description,category,price,stock,weight_kg\n"


def csv_bytes(*rows: str) -> bytes:
    return (HEADER + "".join(row + "\n" for row in rows)).encode("utf-8")


def test_valid_row_is_parsed():
    result = parse(csv_bytes("Running Shoes,RS-001,Light shoes,Footwear,89.99,150,0.35"))

    assert result.errors == []
    row = result.rows[0]
    assert row.sku == "RS-001"
    assert row.price == Decimal("89.99")
    assert row.stock == 150
    assert row.weight_kg == Decimal("0.35")
    assert row.line == 2


def test_currency_symbol_is_stripped_from_price():
    result = parse(csv_bytes("Wireless Mouse,WM-042,Mouse,Electronics,$29.99,75,0.12"))

    assert result.errors == []
    assert result.rows[0].price == Decimal("29.99")


def test_non_numeric_price_is_rejected():
    result = parse(csv_bytes("Yoga Mat,YM-015,Mat,Sports,free,200,1.2"))

    assert result.rows == []
    assert [(e.line, e.field) for e in result.errors] == [(2, "price")]


def test_negative_stock_is_rejected():
    result = parse(csv_bytes("Desk Lamp,DL-007,Lamp,Home & Office,24.99,-5,1.0"))

    assert [(e.field, e.message) for e in result.errors] == [("stock", "must not be negative")]


@pytest.mark.parametrize("name", ["", "     "])
def test_missing_or_whitespace_name_is_rejected(name):
    result = parse(csv_bytes(f"{name},HD-099,Item,Electronics,10.00,5,0.1"))

    assert [e.field for e in result.errors] == ["name"]


def test_missing_category_is_rejected():
    result = parse(csv_bytes("Gift Card,GC-025,Digital card,,25.00,99999,0"))

    assert [e.field for e in result.errors] == ["category"]


def test_blank_weight_becomes_none():
    result = parse(csv_bytes("Gaming Keyboard,GK-088,Keyboard,Electronics,79.99,60,"))

    assert result.errors == []
    assert result.rows[0].weight_kg is None


def test_blank_rows_are_skipped_without_errors():
    result = parse(csv_bytes("Lamp,DL-007,Lamp,Home,24.99,5,1.0", ",,,,,,", ",,,,,,"))

    assert result.blank_rows == 2
    assert result.errors == []
    assert len(result.rows) == 1


def test_sku_is_uppercased():
    result = parse(csv_bytes("Mouse,wm-042,Mouse,Electronics,29.99,75,0.12"))

    assert result.rows[0].sku == "WM-042"


def test_all_invalid_fields_in_a_row_are_reported():
    result = parse(csv_bytes(",BAD-001,Item,,free,-1,"))

    assert {e.field for e in result.errors} == {"name", "category", "price", "stock"}


def test_price_with_too_many_decimal_places_is_rejected():
    result = parse(csv_bytes("Widget,WD-001,Widget,Tools,19.999,5,0.1"))

    assert [e.field for e in result.errors] == ["price"]


def test_non_finite_price_is_rejected():
    result = parse(csv_bytes("Widget,WD-001,Widget,Tools,NaN,5,0.1"))

    assert [e.field for e in result.errors] == ["price"]


def test_line_numbers_follow_the_source_file():
    result = parse(
        csv_bytes(
            "Good,GD-001,Item,Tools,1.00,1,0.1",
            "Bad,BD-001,Item,Tools,free,1,0.1",
        )
    )

    assert result.errors[0].line == 3


def test_value_with_embedded_comma_is_read_as_one_field():
    result = parse(csv_bytes('Coffee,CB-010,"Single origin, medium roast",Food,18.75,500,1.0'))

    assert result.rows[0].description == "Single origin, medium roast"


def test_markup_and_sql_payloads_are_stored_verbatim():
    result = parse(
        csv_bytes(
            "<script>alert('xss')</script>,XS-001,Normal,Electronics,19.99,100,0.1",
            "Robert'); DROP TABLE products;--,SQL-001,Injection test,Games,9.99,50,0.5",
        )
    )

    assert result.errors == []
    assert result.rows[0].name == "<script>alert('xss')</script>"
    assert result.rows[1].name == "Robert'); DROP TABLE products;--"


def test_non_ascii_characters_survive_parsing():
    result = parse(csv_bytes("Water Bottle,WB-033,Steel 1L — cold 24hrs™,Sports,24.99,300,0.45"))

    assert result.rows[0].description == "Steel 1L — cold 24hrs™"


def test_byte_order_mark_is_tolerated():
    result = parse(b"\xef\xbb\xbf" + csv_bytes("Lamp,DL-007,Lamp,Home,24.99,5,1.0"))

    assert result.errors == []
    assert result.rows[0].sku == "DL-007"


def test_unknown_columns_are_ignored_with_a_warning():
    data = (
        "name,sku,description,category,price,stock,weight_kg,colour\n"
        "Lamp,DL-007,Lamp,Home,24.99,5,1.0,red\n"
    ).encode("utf-8")

    result = parse(data)

    assert len(result.rows) == 1
    assert "colour" in result.warnings[0].message


def test_missing_required_column_rejects_the_file():
    data = b"name,sku,description,category,price,stock\nLamp,DL-007,Lamp,Home,24.99,5\n"

    with pytest.raises(CsvFormatError, match="weight_kg"):
        parse(data)


def test_undecodable_bytes_reject_the_file():
    with pytest.raises(CsvFormatError, match="UTF-8"):
        parse(b"\xff\xfe\x00name,sku")


def test_empty_file_is_rejected():
    with pytest.raises(CsvFormatError, match="empty"):
        parse(b"")


def test_overlong_name_is_rejected():
    result = parse(csv_bytes(f"{'x' * 201},LN-001,Item,Tools,1.00,1,0.1"))

    assert [e.field for e in result.errors] == ["name"]


CRLF_HEADER = "name,sku,description,category,price,stock,weight_kg\r\n"


def crlf_bytes(*rows: str) -> bytes:
    return (CRLF_HEADER + "".join(row + "\r\n" for row in rows)).encode("utf-8")


def test_crlf_line_endings_parse_without_errors():
    result = parse(crlf_bytes("Running Shoes,RS-001,Light shoes,Footwear,89.99,150,0.35"))

    assert result.errors == []
    row = result.rows[0]
    assert row.sku == "RS-001"
    assert row.price == Decimal("89.99")
    assert row.stock == 150
    assert row.weight_kg == Decimal("0.35")


def test_carriage_return_does_not_leak_into_the_last_column():
    data = (
        "name,sku,category,price,stock,weight_kg,description\r\n"
        "Running Shoes,RS-001,Footwear,89.99,150,0.35,Light shoes\r\n"
    ).encode("utf-8")

    result = parse(data)

    assert result.errors == []
    assert result.rows[0].description == "Light shoes"


def test_blank_final_field_in_crlf_file_is_missing_not_empty_text():
    result = parse(crlf_bytes("Gaming Keyboard,GK-088,Keyboard,Electronics,79.99,60,"))

    assert result.errors == []
    assert result.rows[0].weight_kg is None


def test_crlf_file_with_quoted_newline_keeps_source_line_numbers():
    data = (
        CRLF_HEADER
        + "Running Shoes,RS-001,Light shoes,Footwear,89.99,150,0.35\r\n"
        + 'Camping Tent,CT-005,"4-person dome,\r\nwaterproof",Outdoors,199.99,25,4.5\r\n'
    ).encode("utf-8")

    result = parse(data)

    assert result.errors == []
    assert [row.line for row in result.rows] == [2, 4]
