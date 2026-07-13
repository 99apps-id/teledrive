from fastapi import Request

from app.core.config import Settings
from app.core import rate_limit


def request_from(peer_ip: str, forwarded_for: str = "") -> Request:
    headers = [(b"x-forwarded-for", forwarded_for.encode())] if forwarded_for else []
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": headers,
            "client": (peer_ip, 12345),
        }
    )


def test_rate_limit_ignores_forwarded_for_from_an_untrusted_peer(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        rate_limit, "settings", Settings(trusted_proxy_cidrs="10.0.0.0/8")
    )

    assert rate_limit.get_rate_limit_key(
        request_from("198.51.100.10", "203.0.113.7")
    ) == "198.51.100.10"


def test_rate_limit_uses_first_forwarded_address_from_a_trusted_peer(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        rate_limit, "settings", Settings(trusted_proxy_cidrs="10.0.0.0/8, ::1/128")
    )

    assert rate_limit.get_rate_limit_key(
        request_from("10.2.3.4", "203.0.113.7, 10.2.3.4")
    ) == "203.0.113.7"


def test_redis_component_settings_encode_password_in_generated_url() -> None:
    settings = Settings(
        redis_url="",
        redis_host="redis.internal",
        redis_port=6380,
        redis_db=2,
        redis_password="pa:ss@word/with?#[]",
    )

    assert (
        settings.redis_url
        == "redis://:pa%3Ass%40word%2Fwith%3F%23%5B%5D@redis.internal:6380/2"
    )


def test_explicit_redis_url_is_preserved() -> None:
    explicit_url = "redis://:external%40password@cache.example:6379/3"

    assert Settings(redis_url=explicit_url).redis_url == explicit_url
