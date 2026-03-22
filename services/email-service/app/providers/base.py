from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseProvider(ABC):
    """Abstract outbound notification provider."""

    @abstractmethod
    def send(self, payload: dict[str, Any]) -> None:
        """
        Deliver a message described by ``payload`` (shape depends on channel).

        Implementations should raise on failure so the worker can retry / DLQ.
        """
        raise NotImplementedError
