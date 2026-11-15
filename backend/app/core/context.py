"""Per-request context available to services (for audit records) without threading
the Request object through every call."""

import ipaddress
from contextvars import ContextVar

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
client_ip_var: ContextVar[str | None] = ContextVar("client_ip", default=None)
user_agent_var: ContextVar[str | None] = ContextVar("user_agent", default=None)


def valid_ip(host: str | None) -> str | None:
    """Return `host` if it is an IP address, else None (e.g. unix sockets, test clients)."""
    if not host:
        return None
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        return None
