from django.views.generic import FormView

from accounts.mixins import StaffRequiredMixin
from importing.forms import CsvUploadForm
from importing.parser import CsvFormatError
from importing.service import import_products


class CsvImportView(StaffRequiredMixin, FormView):
    form_class = CsvUploadForm
    template_name = "importing/upload.html"

    def form_valid(self, form):
        try:
            report = import_products(form.cleaned_data["file"].read())
        except CsvFormatError as error:
            form.add_error("file", str(error))
            return self.form_invalid(form)
        return self.render_to_response(
            self.get_context_data(form=CsvUploadForm(), report=report)
        )
