from ipaddress import ip_address, ip_network

from fastapi import Request
from slowapi import Limiter

from app.core.config import settings


def _peer_is_trusted(peer_ip: str) -> bool:
    try:
        peer_address = ip_address(peer_ip)
    except ValueError:
        return False

    for cidr in settings.trusted_proxy_cidrs.split(","):
        cidr = cidr.strip()
        if not cidr:
            continue
        try:
            if peer_address in ip_network(cidr, strict=False):
                return True
        except ValueError:
            continue
    return False


def get_rate_limit_key(request: Request) -> str:
    """Use forwarded client IPs only when the immediate peer is trusted."""
    peer_ip = request.client.host if request.client else "unknown"
    if not _peer_is_trusted(peer_ip):
        return peer_ip

    forwarded_for = request.headers.get("x-forwarded-for", "")
    client_ip = forwarded_for.split(",", maxsplit=1)[0].strip()
    return client_ip or peer_ip


limiter = Limiter(key_func=get_rate_limit_key)
