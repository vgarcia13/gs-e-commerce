import logging

from django.views.generic import FormView

from accounts.mixins import StaffRequiredMixin
from importing.forms import CsvUploadForm
from importing.parser import CsvFormatError
from importing.service import import_products


logger = logging.getLogger(__name__)


class CsvImportView(StaffRequiredMixin, FormView):
    form_class = CsvUploadForm
    template_name = "importing/upload.html"

    def form_valid(self, form):
        upload = form.cleaned_data["file"]
        logger.info(
            "CSV upload %s (%s bytes) received from user %s",
            upload.name,
            upload.size,
            self.request.user.pk,
            extra={
                "event": "import.upload_received",
                "actor_id": self.request.user.pk,
                "upload_filename": upload.name,
                "bytes": upload.size,
            },
        )
        try:
            report = import_products(upload.read())
        except CsvFormatError as error:
            form.add_error("file", str(error))
            return self.form_invalid(form)
        return self.render_to_response(
            self.get_context_data(form=CsvUploadForm(), report=report)
        )
