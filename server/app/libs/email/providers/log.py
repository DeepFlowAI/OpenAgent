import logging
from app.libs.email.base import BaseEmailSender

logger = logging.getLogger(__name__)


class LogEmailSender(BaseEmailSender):
    """Fallback sender that logs emails instead of sending them."""

    async def send(self, to: str, subject: str, body: str) -> None:
        logger.info("EMAIL [to=%s] subject=%s\n%s", to, subject, body)
