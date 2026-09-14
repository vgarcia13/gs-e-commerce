import logging

from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(user_logged_in)
def log_login(sender, request, user, **kwargs) -> None:
    logger.info(
        "User %s logged in",
        user.pk,
        extra={"event": "auth.login_succeeded", "actor_id": user.pk, "is_staff": user.is_staff},
    )


@receiver(user_logged_out)
def log_logout(sender, request, user, **kwargs) -> None:
    if user is None:
        return
    logger.info(
        "User %s logged out",
        user.pk,
        extra={"event": "auth.logout", "actor_id": user.pk},
    )


@receiver(user_login_failed)
def log_login_failure(sender, credentials, request=None, **kwargs) -> None:
    logger.warning(
        "Failed login for %s",
        credentials.get("username", ""),
        extra={
            "event": "auth.login_failed",
            "attempted_username": credentials.get("username", ""),
        },
    )
