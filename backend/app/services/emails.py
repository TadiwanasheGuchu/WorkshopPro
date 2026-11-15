"""Account email content. Links use URL fragments (#token=...) so tokens are not sent
to servers or written to access logs when the page loads."""

from app.core.config import get_settings
from app.integrations.email import OutgoingEmail


def invitation_email(
    *, to: str, full_name: str, organisation_name: str, token: str
) -> OutgoingEmail:
    settings = get_settings()
    link = f"{settings.app_base_url}/accept-invitation#token={token}"
    return OutgoingEmail(
        to=to,
        subject=f"You have been invited to {organisation_name} on WorkshopPro",
        text=(
            f"Hello {full_name},\n\n"
            f"You have been invited to join {organisation_name} on WorkshopPro.\n\n"
            f"Set your password and activate your account:\n{link}\n\n"
            f"This link expires in {settings.invitation_token_days} days and can be used once.\n"
            "If you were not expecting this invitation, you can ignore this email.\n"
        ),
    )


def password_reset_email(*, to: str, full_name: str, token: str) -> OutgoingEmail:
    settings = get_settings()
    link = f"{settings.app_base_url}/reset-password#token={token}"
    return OutgoingEmail(
        to=to,
        subject="Reset your WorkshopPro password",
        text=(
            f"Hello {full_name},\n\n"
            "We received a request to reset your WorkshopPro password.\n\n"
            f"Choose a new password:\n{link}\n\n"
            f"This link expires in {settings.password_reset_token_minutes} minutes and can be "
            "used once. If you did not request this, you can ignore this email; your password "
            "has not changed.\n"
        ),
    )
