from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from importing.parser import CsvFormatError
from importing.service import import_products


class Command(BaseCommand):
    help = "Import products from a CSV file, upserting by SKU."

    def add_arguments(self, parser):
        parser.add_argument("path", type=Path)

    def handle(self, *args, **options):
        path = options["path"]
        try:
            data = path.read_bytes()
        except OSError as error:
            raise CommandError(f"Cannot read {path}: {error}") from error

        try:
            report = import_products(data)
        except CsvFormatError as error:
            raise CommandError(str(error)) from error

        self.stdout.write(
            f"created {report.created}, updated {report.updated}, "
            f"resurrected {report.resurrected}, rejected {report.rejected}, "
            f"blank rows skipped {report.blank_rows}"
        )
        for warning in report.warnings:
            self.stdout.write(self.style.WARNING(f"warning: {warning}"))
        for error in report.errors:
            self.stdout.write(self.style.ERROR(f"rejected: {error}"))
