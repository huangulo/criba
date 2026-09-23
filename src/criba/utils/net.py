"""Guards for outbound HTTP requests."""

import asyncio
import ipaddress
from urllib.parse import urlparse

ALLOWED_SCHEMES = ("http", "https")


async def assert_public_http_url(url: str) -> None:
    """Raise ValueError unless url is an http(s) URL resolving to public addresses.

    Blocks loopback, private, link-local, and other non-global destinations.
    Used as an httpx request event hook it is applied to every redirect hop
    as well as the original request.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise ValueError(f"URL scheme {parsed.scheme!r} is not allowed")
    host = parsed.hostname
    if not host:
        raise ValueError("URL has no hostname")

    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, None)
    except OSError as exc:
        raise ValueError(f"cannot resolve host {host!r}: {exc}") from exc

    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if not address.is_global:
            raise ValueError(f"host {host!r} resolves to non-public address {address}")
