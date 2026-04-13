import logging
import os
from urllib.parse import urlsplit

import aiohttp

logger = logging.getLogger(__name__)


def normalize_proxy_url(proxy_url: str | None) -> str | None:
    if not proxy_url:
        return None

    if proxy_url.startswith("socks5h://"):
        return proxy_url.replace("socks5h://", "socks5://", 1)

    return proxy_url


def get_telegram_proxy_recheck_url(proxy_url: str | None) -> str | None:
    explicit = os.getenv("TELEGRAM_PROXY_RECHECK_URL")
    if explicit:
        return explicit.strip()

    normalized_proxy_url = normalize_proxy_url(proxy_url)
    if not normalized_proxy_url:
        return None

    parsed = urlsplit(normalized_proxy_url)
    if parsed.hostname != "proxy":
        return None

    return "http://proxy:8080/recheck?group=telegram"


def build_telegram_http_client_config(
    timeout: aiohttp.ClientTimeout, proxy_url: str | None, *, log_context: str = "Telegram session"
) -> tuple[dict[str, object], dict[str, object]]:
    normalized_proxy_url = normalize_proxy_url(proxy_url)
    session_kwargs: dict[str, object] = {"timeout": timeout}
    request_kwargs: dict[str, object] = {}

    if not normalized_proxy_url:
        return session_kwargs, request_kwargs

    logger.info("Using proxy for %s: %s", log_context, normalized_proxy_url)

    if normalized_proxy_url.startswith("socks"):
        from aiohttp_socks import ProxyConnector

        session_kwargs["connector"] = ProxyConnector.from_url(normalized_proxy_url)
    else:
        request_kwargs["proxy"] = normalized_proxy_url

    return session_kwargs, request_kwargs
