from abc import ABC, abstractmethod


class BaseEmailSender(ABC):
    @abstractmethod
    async def send(self, to: str, subject: str, body: str) -> None:
        """Send a plain-text email."""
        ...
