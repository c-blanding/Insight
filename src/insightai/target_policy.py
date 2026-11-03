"""Policy for URLs passed to the browser runtime.

Hosted runs are deny-by-default for non-public destinations. Local targets must
be explicitly listed in ``INSIGHT_LOCAL_TARGETS``; public targets may be
restricted further with ``INSIGHT_ALLOWED_TARGET_HOSTS``.
"""

from __future__ import annotations

import ipaddress
import os
import socket
from urllib.parse import urlsplit


class TargetPolicyError(ValueError):
    """A target URL is outside the configured browser-access policy."""


def _host_list(name: str) -> set[str]:
    return {
        item.strip().rstrip(".").lower()
        for item in (os.environ.get(name) or "").split(",")
        if item.strip()
    }


def _is_public_address(value: str) -> bool:
    address = ipaddress.ip_address(value)
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    return address.is_global


def validate_target_url(url: str) -> str:
    """Validate scheme, authority, port, hostname allowlist, and DNS answers.

    Returns the normalized hostname. DNS is resolved for every navigation so
    policy changes and rebinding attempts are checked at the tool boundary.
    """
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise TargetPolicyError("Target URL has an invalid host or port") from exc

    if parsed.scheme.lower() not in {"http", "https"}:
        raise TargetPolicyError("Target URL must use http or https")
    if not parsed.hostname or parsed.username is not None or parsed.password is not None:
        raise TargetPolicyError("Target URL must include a host and no embedded credentials")
    host = parsed.hostname.rstrip(".").lower()
    if not host or any(ch.isspace() for ch in host):
        raise TargetPolicyError("Target URL has an invalid hostname")

    local_hosts = _host_list("INSIGHT_LOCAL_TARGETS")
    public_hosts = _host_list("INSIGHT_ALLOWED_TARGET_HOSTS")
    is_local = host in local_hosts
    if is_local and port is not None and not 1 <= port <= 65535:
        raise TargetPolicyError("Target URL port is invalid")
    if not is_local and port not in {None, 80, 443}:
        raise TargetPolicyError("Hosted target URLs may use only ports 80 and 443")
    if not is_local and not public_hosts:
        raise TargetPolicyError(
            "No public targets are configured; set INSIGHT_ALLOWED_TARGET_HOSTS"
        )
    if not is_local and host not in public_hosts:
        raise TargetPolicyError("Target host is not in INSIGHT_ALLOWED_TARGET_HOSTS")

    try:
        answers = socket.getaddrinfo(host, port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
    except OSError as exc:
        raise TargetPolicyError("Target hostname could not be resolved") from exc
    addresses = {answer[4][0].split("%", 1)[0] for answer in answers}
    if not addresses:
        raise TargetPolicyError("Target hostname has no addresses")
    if is_local and any(_is_public_address(address) for address in addresses):
        raise TargetPolicyError("Local target hostname resolves to a public address")
    if not is_local and not all(_is_public_address(address) for address in addresses):
        raise TargetPolicyError("Target hostname resolves to a non-public address")
    return host
