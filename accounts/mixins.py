import logging

from django.contrib import messages
from django.contrib.auth.mixins import UserPassesTestMixin
from django.shortcuts import redirect

logger = logging.getLogger(__name__)


class StaffRequiredMixin(UserPassesTestMixin):
    permission_denied_message = "That section is staff only."

    def test_func(self) -> bool:
        return self.request.user.is_staff

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            logger.warning(
                "User %s was denied access to %s",
                self.request.user.pk,
                self.request.path,
                extra={
                    "event": "auth.access_denied",
                    "actor_id": self.request.user.pk,
                    "path": self.request.path,
                },
            )
            messages.warning(self.request, self.permission_denied_message)
            return redirect("catalog:product_list")
        return super().handle_no_permission()
