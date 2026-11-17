"""Errors shared by message delivery adaptors (email, WhatsApp).

TransientDeliveryError: worth retrying (network, timeouts, rate limits, 5xx).
PermanentDeliveryError: retrying will not help (invalid number, rejected template, 4xx).
"""


class DeliveryError(Exception):
    pass


class TransientDeliveryError(DeliveryError):
    pass


class PermanentDeliveryError(DeliveryError):
    pass
