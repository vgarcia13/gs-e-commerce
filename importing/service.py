import logging

from django.db import DataError, IntegrityError, transaction

from catalog.models import Product
from importing.parser import CsvFormatError, ProductRow, parse
from importing.results import ImportReport, RowError, RowWarning

logger = logging.getLogger(__name__)

CREATED = "created"
UPDATED = "updated"
RESURRECTED = "resurrected"


def _collapse_duplicates(rows: list[ProductRow]) -> tuple[list[ProductRow], list[RowWarning]]:
    latest: dict[str, ProductRow] = {}
    superseded: dict[str, list[int]] = {}
    for row in rows:
        previous = latest.get(row.sku)
        if previous is not None:
            superseded.setdefault(row.sku, []).append(previous.line)
        latest[row.sku] = row
    warnings = [
        RowWarning(
            line=latest[sku].line,
            message=(
                f"SKU {sku} appears more than once; "
                f"superseded line(s) {', '.join(str(line) for line in lines)}"
            ),
        )
        for sku, lines in superseded.items()
    ]
    return list(latest.values()), warnings


def _find_existing(sku: str) -> Product | None:
    active = Product.objects.filter(sku=sku, deleted_at__isnull=True).first()
    if active is not None:
        return active
    return Product.objects.filter(sku=sku).order_by("-deleted_at").first()


def _upsert(row: ProductRow) -> str:
    product = _find_existing(row.sku)
    if product is None:
        Product.objects.create(
            name=row.name,
            sku=row.sku,
            description=row.description,
            category=row.category,
            price=row.price,
            stock=row.stock,
            weight_kg=row.weight_kg,
        )
        return CREATED

    was_deleted = product.deleted_at is not None
    product.name = row.name
    product.category = row.category
    product.price = row.price
    if row.description:
        product.description = row.description
    if row.weight_kg is not None:
        product.weight_kg = row.weight_kg
    if was_deleted:
        product.deleted_at = None
        product.stock = row.stock
    product.save()
    return RESURRECTED if was_deleted else UPDATED


def import_products(data: bytes) -> ImportReport:
    """Upserts products from CSV bytes, skipping and reporting rows that fail validation."""
    logger.info(
        "Product import started (%s bytes)",
        len(data),
        extra={"event": "import.started", "bytes": len(data)},
    )
    try:
        parsed = parse(data)
    except CsvFormatError as error:
        logger.warning(
            "Product import rejected the file: %s",
            error,
            extra={"event": "import.file_rejected", "reason": str(error)},
        )
        raise
    report = ImportReport(blank_rows=parsed.blank_rows)
    report.errors.extend(parsed.errors)
    report.warnings.extend(parsed.warnings)

    rows, duplicate_warnings = _collapse_duplicates(parsed.rows)
    report.warnings.extend(duplicate_warnings)

    for row in rows:
        try:
            with transaction.atomic():
                outcome = _upsert(row)
        except (IntegrityError, DataError) as error:
            logger.exception(
                "Database rejected line %s (SKU %s)",
                row.line,
                row.sku,
                extra={"event": "import.row_failed", "line": row.line, "sku": row.sku},
            )
            report.errors.append(
                RowError(
                    line=row.line,
                    field=None,
                    value=row.sku,
                    message=str(error).strip().splitlines()[0],
                )
            )
            continue
        setattr(report, outcome, getattr(report, outcome) + 1)

    logger.info(
        "Product import finished: created=%s updated=%s resurrected=%s rejected=%s blank=%s",
        report.created,
        report.updated,
        report.resurrected,
        report.rejected,
        report.blank_rows,
        extra={
            "event": "import.completed",
            "products_created": report.created,
            "products_updated": report.updated,
            "products_resurrected": report.resurrected,
            "rows_rejected": report.rejected,
            "rows_blank": report.blank_rows,
        },
    )
    if report.errors:
        logger.warning(
            "Product import rejected %s row(s)",
            report.rejected,
            extra={"event": "import.rows_rejected", "rows_rejected": report.rejected},
        )

    return report
