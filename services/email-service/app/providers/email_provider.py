from __future__ import annotations

from app.providers.base import BaseProvider


class EmailProvider(BaseProvider):
    """
    Email channel contract.

    Expected ``payload`` keys for OTP jobs:

    - ``to``: recipient address
    - ``otp``: code
    - ``client_name``: optional display name for the body
    - ``subject``: optional override (default set by implementation)
    """
