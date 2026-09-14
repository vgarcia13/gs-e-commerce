from django import forms

MAX_UPLOAD_BYTES = 5 * 1024 * 1024


class CsvUploadForm(forms.Form):
    file = forms.FileField(label="CSV file")

    def clean_file(self):
        uploaded = self.cleaned_data["file"]
        if uploaded.size > MAX_UPLOAD_BYTES:
            raise forms.ValidationError(
                f"File is larger than the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit."
            )
        return uploaded
