from app.configs.settings import settings
from app.libs.email.base import BaseEmailSender


def create_email_sender() -> BaseEmailSender:
    if settings.SMTP_HOST:
        from app.libs.email.providers.smtp import SmtpEmailSender
        return SmtpEmailSender()
    from app.libs.email.providers.log import LogEmailSender
    return LogEmailSender()
