"""Restore a visitor address only through the configured Cloudflare/Fly chain."""

from __future__ import annotations

from ipaddress import IPv4Address, IPv6Address, ip_address
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ipaddress import IPv4Network, IPv6Network

    from starlette.requests import Request


def _address(request: Request, header: str) -> IPv4Address | IPv6Address | None:
    values = request.headers.getlist(header)
    if len(values) != 1 or "%" in values[0]:
        return None
    try:
        return ip_address(values[0].strip())
    except ValueError:
        return None


def cloudflare_identity(
    request: Request, networks: tuple[IPv4Network | IPv6Network, ...]
) -> str:
    """Fly supplies the peer; only Cloudflare peers may supply visitor identity.

    The service must be reachable through Fly's ingress for Fly-Client-IP to be
    authoritative. Worker subrequests use the peer because a Worker targeting
    the direct Fly hostname can supply its own CF-Connecting-IP value.
    """
    peer = _address(request, "Fly-Client-IP")
    if peer is None:
        return request.client.host if request.client else "unknown"
    if "cf-worker" in request.headers:
        return str(peer)
    if not any(peer in network for network in networks):
        return str(peer)
    visitor = _address(request, "CF-Connecting-IP")
    return str(visitor or peer)
