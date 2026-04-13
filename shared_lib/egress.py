import os
from urllib.parse import SplitResult, urlsplit, urlunsplit


def get_telegram_proxy_transport() -> str:
    raw_transport = (os.getenv("TELEGRAM_PROXY_TRANSPORT") or "auto").strip().lower()
    if raw_transport in {"socks", "tcp"}:
        return "socks"
    if raw_transport == "http":
        return "http"
    return "auto"


def get_telegram_proxy_url() -> str | None:
    raw_proxy_url = os.getenv("TELEGRAM_PROXY_URL") or os.getenv("PROXY_URL")
    if not raw_proxy_url:
        return None

    parsed = urlsplit(raw_proxy_url)
    transport = get_telegram_proxy_transport()

    if transport == "socks":
        return raw_proxy_url

    if transport == "http" and parsed.scheme.startswith("socks"):
        http_proxy = SplitResult(
            scheme="http",
            netloc=parsed.netloc,
            path=parsed.path,
            query=parsed.query,
            fragment=parsed.fragment,
        )
        return urlunsplit(http_proxy)

    if parsed.scheme.startswith("socks") and parsed.hostname == "proxy":
        # The local mihomo container exposes a mixed HTTP+SOCKS listener.
        # Using HTTP proxy mode avoids the aiohttp_socks TLS handshake path that
        # has been resetting bot startup traffic in production.
        http_proxy = SplitResult(
            scheme="http",
            netloc=parsed.netloc,
            path=parsed.path,
            query=parsed.query,
            fragment=parsed.fragment,
        )
        return urlunsplit(http_proxy)

    return raw_proxy_url


def get_global_http_proxy_url() -> str | None:
    return os.getenv("GLOBAL_HTTP_PROXY_URL") or os.getenv("PROXY_URL")


def normalize_env_proxy_url(proxy_url: str | None) -> str | None:
    if not proxy_url:
        return None

    if proxy_url.startswith("socks5://"):
        return proxy_url.replace("socks5://", "socks5h://", 1)

    return proxy_url


def _merge_no_proxy(existing: str | None, no_proxy_hosts: tuple[str, ...]) -> str:
    merged: list[str] = []
    seen: set[str] = set()

    for raw_value in (existing or "").split(","):
        value = raw_value.strip()
        if value and value not in seen:
            merged.append(value)
            seen.add(value)

    for value in no_proxy_hosts:
        normalized = value.strip()
        if normalized and normalized not in seen:
            merged.append(normalized)
            seen.add(normalized)

    return ",".join(merged)


def configure_process_http_proxy_env(
    proxy_url: str | None, *, no_proxy_hosts: tuple[str, ...] = ()
) -> None:
    normalized_proxy_url = normalize_env_proxy_url(proxy_url)
    if normalized_proxy_url:
        os.environ["HTTP_PROXY"] = normalized_proxy_url
        os.environ["HTTPS_PROXY"] = normalized_proxy_url
        os.environ["ALL_PROXY"] = normalized_proxy_url

    if no_proxy_hosts:
        merged = _merge_no_proxy(os.getenv("NO_PROXY"), no_proxy_hosts)
        os.environ["NO_PROXY"] = merged
        os.environ["no_proxy"] = merged
