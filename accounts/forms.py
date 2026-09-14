from django.contrib.auth.forms import AuthenticationForm, BaseUserCreationForm

from accounts.models import User


class SignupForm(BaseUserCreationForm):
    class Meta(BaseUserCreationForm.Meta):
        model = User
        fields = ("email",)

    def clean_email(self) -> str:
        return self.cleaned_data["email"].strip().lower()


class EmailAuthenticationForm(AuthenticationForm):
    def clean_username(self) -> str:
        return self.cleaned_data["username"].strip().lower()
