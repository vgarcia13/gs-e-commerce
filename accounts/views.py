import logging

from django.contrib.auth import login
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView

from accounts.forms import SignupForm


logger = logging.getLogger(__name__)


class SignupView(CreateView):
    form_class = SignupForm
    template_name = "accounts/signup.html"
    success_url = reverse_lazy("catalog:product_list")

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect(self.success_url)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)
        logger.info(
            "Account created for user %s",
            self.object.pk,
            extra={"event": "auth.signup", "actor_id": self.object.pk},
        )
        login(self.request, self.object)
        return response
