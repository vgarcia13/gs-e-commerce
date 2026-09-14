import csv
import dataclasses
import io
import re
from decimal import Decimal, InvalidOperation

from catalog.models import Product
from importing.results import RowError, RowWarning

REQUIRED_COLUMNS = ("name", "sku", "description", "category", "price", "stock", "weight_kg")
HEADER_LINE = 1
PRICE_DECIMAL_PLACES = 2
WEIGHT_DECIMAL_PLACES = 3
WHOLE_NUMBER = re.compile(r"^-?\d+$")


class CsvFormatError(Exception):
    pass


class FieldError(Exception):
    def __init__(self, field: str, value: str, message: str):
        super().__init__(message)
        self.field = field
        self.value = value
        self.message = message


@dataclasses.dataclass(frozen=True)
class ProductRow:
    line: int
    name: str
    sku: str
    description: str
    category: str
    price: Decimal
    stock: int
    weight_kg: Decimal | None


@dataclasses.dataclass
class ParseResult:
    rows: list[ProductRow] = dataclasses.field(default_factory=list)
    errors: list[RowError] = dataclasses.field(default_factory=list)
    warnings: list[RowWarning] = dataclasses.field(default_factory=list)
    blank_rows: int = 0


def _max_length(field: str) -> int:
    return Product._meta.get_field(field).max_length


def _text(field: str, raw: str | None, *, required: bool, upper: bool = False) -> str:
    value = (raw or "").strip()
    if upper:
        value = value.upper()
    if required and not value:
        raise FieldError(field, raw or "", "is required")
    limit = _max_length(field)
    if len(value) > limit:
        raise FieldError(field, value, f"must be at most {limit} characters")
    return value


def _decimal(field: str, raw: str | None, *, places: int) -> Decimal:
    value = (raw or "").strip()
    if value.startswith("$"):
        value = value[1:].strip()
    try:
        number = Decimal(value)
    except InvalidOperation:
        raise FieldError(field, raw or "", "is not a valid decimal number") from None
    if not number.is_finite():
        raise FieldError(field, raw or "", "is not a finite number")
    if number < 0:
        raise FieldError(field, raw or "", "must not be negative")
    if -number.as_tuple().exponent > places:
        raise FieldError(field, raw or "", f"must not have more than {places} decimal places")
    return number


def _price(raw: str | None) -> Decimal:
    if not (raw or "").strip():
        raise FieldError("price", raw or "", "is required")
    return _decimal("price", raw, places=PRICE_DECIMAL_PLACES)


def _weight(raw: str | None) -> Decimal | None:
    if not (raw or "").strip():
        return None
    return _decimal("weight_kg", raw, places=WEIGHT_DECIMAL_PLACES)


def _stock(raw: str | None) -> int:
    value = (raw or "").strip()
    if not value:
        raise FieldError("stock", raw or "", "is required")
    if not WHOLE_NUMBER.match(value):
        raise FieldError("stock", raw or "", "is not a whole number")
    number = int(value)
    if number < 0:
        raise FieldError("stock", raw or "", "must not be negative")
    return number


def _parse_row(line: int, raw: dict) -> tuple[ProductRow | None, list[RowError]]:
    errors: list[RowError] = []
    values: dict = {}
    coercions = (
        ("name", lambda: _text("name", raw.get("name"), required=True)),
        ("sku", lambda: _text("sku", raw.get("sku"), required=True, upper=True)),
        ("description", lambda: (raw.get("description") or "").strip()),
        ("category", lambda: _text("category", raw.get("category"), required=True)),
        ("price", lambda: _price(raw.get("price"))),
        ("stock", lambda: _stock(raw.get("stock"))),
        ("weight_kg", lambda: _weight(raw.get("weight_kg"))),
    )
    for field, coerce in coercions:
        try:
            values[field] = coerce()
        except FieldError as error:
            errors.append(
                RowError(line=line, field=error.field, value=error.value, message=error.message)
            )
    if errors:
        return None, errors
    return ProductRow(line=line, **values), []


def _is_blank(raw: dict) -> bool:
    return all(not (value or "").strip() for key, value in raw.items() if key in REQUIRED_COLUMNS)


def parse(data: bytes) -> ParseResult:
    """Decodes and validates CSV bytes, reporting failures against their source line numbers."""
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise CsvFormatError("File is not valid UTF-8 text.") from error

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise CsvFormatError("File is empty.")

    reader.fieldnames = [(name or "").strip() for name in reader.fieldnames]
    missing = [column for column in REQUIRED_COLUMNS if column not in reader.fieldnames]
    if missing:
        raise CsvFormatError(f"Missing required column(s): {', '.join(missing)}.")

    result = ParseResult()
    unknown = [name for name in reader.fieldnames if name not in REQUIRED_COLUMNS]
    if unknown:
        result.warnings.append(
            RowWarning(line=HEADER_LINE, message=f"Ignoring unknown column(s): {', '.join(unknown)}.")
        )

    for raw in reader:
        line = reader.line_num
        if _is_blank(raw):
            result.blank_rows += 1
            continue
        row, errors = _parse_row(line, raw)
        if row is None:
            result.errors.extend(errors)
        else:
            result.rows.append(row)
    return result
