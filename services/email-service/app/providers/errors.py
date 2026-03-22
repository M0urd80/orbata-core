"""Errors from outbound delivery backends (Twilio, SMTP, etc.)."""


class ProviderError(Exception):
    """
    Raised when a provider fails to send after exhausting failover (or env fallback fails).

    The worker retries only this type — validation / payload errors are not retried.
    """
