import base64
import hashlib
import json
import os
import re
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlencode, urlsplit, urlunsplit

CACHE_FILE = "/app/cache/last_good_sub.yaml"
CONTROLLER_URL = os.environ.get("MIHOMO_CONTROLLER_URL", "http://127.0.0.1:9090")
PROXY_HTTP_BIND = os.environ.get("PROXY_HTTP_BIND", "0.0.0.0")
SUB_URLS_FILE = os.environ.get("SUB_URLS_FILE", "/run/secrets/proxy-subscriptions.json")
MAX_SUBSCRIPTION_SOURCES = 32
SUBSCRIPTION_FETCH_TIMEOUT_SECONDS = 15
CACHE_REFRESH_INTERVAL_SECONDS = 300

CACHE_LOCK = threading.Lock()
BUILD_LOCK = threading.Lock()
REFRESH_THREAD_LOCK = threading.Lock()
REFRESH_THREAD = None

STATE = {
    "last_build": None,
    "last_cache_write": None,
}


def safe_dict(d):
    return d if isinstance(d, dict) else {}


def safe_list(value):
    return value if isinstance(value, list) else []


def quote_yaml_scalar(value):
    return json.dumps(str(value), ensure_ascii=False)


def append_yaml_field(lines, key, value, indent="    "):
    if value is None:
        return

    if isinstance(value, bool):
        rendered = "true" if value else "false"
    elif isinstance(value, (int, float)):
        rendered = str(value)
    else:
        value_str = str(value)
        if not value_str.strip():
            return
        rendered = quote_yaml_scalar(value_str)

    lines.append(f"{indent}{key}: {rendered}")


def append_yaml_list(lines, key, values, indent="    "):
    cleaned = [str(value) for value in safe_list(values) if str(value).strip()]
    if not cleaned:
        return

    lines.append(f"{indent}{key}:")
    for value in cleaned:
        lines.append(f"{indent}- {quote_yaml_scalar(value)}")


def replace_json_surrogate_pairs(value):
    pattern = re.compile(r"\\u([dD][89aAbB][0-9a-fA-F]{2})\\u([dD][c-fC-F][0-9a-fA-F]{2})")

    def replace(match):
        high = int(match.group(1), 16)
        low = int(match.group(2), 16)
        codepoint = 0x10000 + ((high - 0xD800) << 10) + (low - 0xDC00)
        return chr(codepoint)

    return pattern.sub(replace, value)


def normalize_legacy_ss_plugin_yaml(value):
    value = re.sub(
        r'(?m)^(\s*)plugin:\s*["\']?obfs-local["\']?\s*$',
        r'\1plugin: "obfs"',
        value,
    )
    value = re.sub(r"(?m)^(\s{6,})obfs:\s*", r"\1mode: ", value)
    return re.sub(r"(?m)^(\s{6,})obfs-host:\s*", r"\1host: ", value)


def _decode_base64_urlsafe(value):
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}").decode("utf-8")


def parse_outline_ss_uri(uri):
    parsed = urlsplit(uri.strip())
    if parsed.scheme != "ss":
        return None

    method = parsed.username
    password = parsed.password
    if method and password:
        return {
            "server": parsed.hostname,
            "server_port": parsed.port,
            "method": method,
            "password": password,
            "prefix": parse_qs(parsed.query).get("prefix", [None])[0],
        }

    userinfo = parsed.netloc.split("@", 1)[0]
    if not userinfo:
        return None

    try:
        decoded = _decode_base64_urlsafe(userinfo)
        method, password = decoded.split(":", 1)
    except Exception:
        return None

    return {
        "server": parsed.hostname,
        "server_port": parsed.port,
        "method": method,
        "password": password,
        "prefix": parse_qs(parsed.query).get("prefix", [None])[0],
    }


def build_outline_mihomo_yaml(config, *, name="outline"):
    server = config.get("server")
    port = config.get("server_port")
    method = config.get("method")
    password = config.get("password")
    if not (server and port and method and password):
        return None

    yaml_lines = [
        "proxies:",
        f"  - name: {quote_yaml_scalar(name)}",
        "    type: ss",
        f"    server: {quote_yaml_scalar(server)}",
        f"    port: {port}",
        f"    cipher: {quote_yaml_scalar(method)}",
        f"    password: {quote_yaml_scalar(password)}",
        "    udp: true",
    ]
    append_yaml_field(yaml_lines, "prefix", config.get("prefix"))
    return "\n".join(yaml_lines)


def extract_proxy_entries(yaml_text):
    if not yaml_text:
        return []

    lines = str(yaml_text).splitlines()
    try:
        start_idx = next(i for i, line in enumerate(lines) if line.strip() == "proxies:")
    except StopIteration:
        return []

    return [line for line in lines[start_idx + 1 :] if line.strip()]


def merge_proxy_yaml_documents(*yaml_documents):
    merged_entries = []
    seen_names = set()

    for yaml_text in yaml_documents:
        current_entry = []

        for line in extract_proxy_entries(yaml_text):
            if line.startswith("  - name:"):
                if current_entry:
                    proxy_name = current_entry[0].split(":", 1)[1].strip()
                    if proxy_name not in seen_names:
                        merged_entries.extend(current_entry)
                        seen_names.add(proxy_name)
                current_entry = [line]
            elif current_entry:
                current_entry.append(line)

        if current_entry:
            proxy_name = current_entry[0].split(":", 1)[1].strip()
            if proxy_name not in seen_names:
                merged_entries.extend(current_entry)
                seen_names.add(proxy_name)

    if not merged_entries:
        return None

    return "\n".join(["proxies:", *merged_entries])


def _outline_url_to_fetch(access_key):
    parsed = urlsplit(access_key.strip())
    if parsed.scheme in {"http", "https"}:
        return access_key.strip()
    if parsed.scheme == "ssconf":
        return urlunsplit(("https", parsed.netloc, parsed.path, parsed.query, ""))
    return None


def process_outline_dynamic_payload(raw_data):
    raw_text = raw_data.strip()
    if not raw_text:
        return None

    if raw_text.startswith("ss://"):
        outline = parse_outline_ss_uri(raw_text)
        return build_outline_mihomo_yaml(outline) if outline else None

    try:
        parsed_json = json.loads(raw_text)
    except Exception:
        return None

    if isinstance(parsed_json, dict):
        if "server" in parsed_json and "server_port" in parsed_json:
            return build_outline_mihomo_yaml(parsed_json)
        nested_ss = (
            parsed_json.get("accessKey") or parsed_json.get("ssUri") or parsed_json.get("uri")
        )
        if isinstance(nested_ss, str) and nested_ss.startswith("ss://"):
            outline = parse_outline_ss_uri(nested_ss)
            return build_outline_mihomo_yaml(outline) if outline else None

    return None


def load_outline_yaml():
    access_key = os.environ.get("OUTLINE_ACCESS_KEY")
    if not access_key:
        return None

    access_key = access_key.strip()
    if access_key.startswith("ss://"):
        outline = parse_outline_ss_uri(access_key)
        return build_outline_mihomo_yaml(outline) if outline else None

    fetch_url = _outline_url_to_fetch(access_key)
    if not fetch_url:
        return None

    req = urllib.request.Request(fetch_url, headers={"User-Agent": "Outline-Access-Key"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        raw = resp.read().decode("utf-8", errors="ignore")
    return process_outline_dynamic_payload(raw)


def _safe_fetch_error(exc):
    status = getattr(exc, "code", None)
    if status is not None:
        return f"{type(exc).__name__} (HTTP {status})"
    return type(exc).__name__


def _validated_subscription_url(value):
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not candidate:
        return None
    try:
        parsed = urlsplit(candidate)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    return candidate


def load_subscription_urls():
    """Load ordered subscription URLs without ever logging their bearer values."""

    candidates = []
    legacy_url = _validated_subscription_url(os.environ.get("SUB_URL"))
    if legacy_url:
        candidates.append(legacy_url)

    if SUB_URLS_FILE and os.path.isfile(SUB_URLS_FILE):
        with open(SUB_URLS_FILE, encoding="utf-8") as source_file:
            payload = json.load(source_file)
        if isinstance(payload, dict):
            payload = payload.get("urls", [])
        if not isinstance(payload, list):
            raise ValueError(
                "subscription URL file must contain a JSON list or an object with urls"
            )
        candidates.extend(payload)

    urls = []
    seen = set()
    for value in candidates:
        validated = _validated_subscription_url(value)
        if not validated or validated in seen:
            continue
        seen.add(validated)
        urls.append(validated)
        if len(urls) >= MAX_SUBSCRIPTION_SOURCES:
            break
    return urls


def load_subscription_yaml():
    urls = load_subscription_urls()
    documents = []
    source_results = []
    payload_hashes = set()
    duplicate_payloads = 0
    unsupported_protocols = {}

    def fetch(url):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "v2rayNG/1.8.5"})
            with urllib.request.urlopen(req, timeout=SUBSCRIPTION_FETCH_TIMEOUT_SECONDS) as resp:
                return resp.read().decode("utf-8", errors="ignore").strip(), None
        except Exception as exc:
            return None, _safe_fetch_error(exc)

    if urls:
        with ThreadPoolExecutor(max_workers=min(8, len(urls))) as executor:
            downloads = list(executor.map(fetch, urls))
    else:
        downloads = []

    for source_index, (url, download) in enumerate(zip(urls, downloads), start=1):
        source_label = f"source-{source_index}"
        result = {"source": source_label, "loaded": False, "entries": 0}
        raw, fetch_error = download
        if fetch_error:
            result["error"] = fetch_error
            source_results.append(result)
            continue
        try:
            payload_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
            if payload_hash in payload_hashes:
                duplicate_payloads += 1
                result["duplicate_payload"] = True
                source_results.append(result)
                continue
            payload_hashes.add(payload_hash)

            yaml_text, details = process_subscription_payload(
                raw,
                name_prefix=f"s{source_index}",
            )
            for protocol, count in details.get("unsupported_protocols", {}).items():
                unsupported_protocols[protocol] = unsupported_protocols.get(protocol, 0) + count
            if yaml_text:
                result["loaded"] = True
                result["entries"] = len(
                    [
                        line
                        for line in extract_proxy_entries(yaml_text)
                        if line.startswith("  - name:")
                    ]
                )
                documents.append(yaml_text)
            else:
                result["error"] = "no supported proxy nodes"
        except Exception as exc:
            result["error"] = _safe_fetch_error(exc)
        source_results.append(result)

    combined = merge_proxy_yaml_documents(*documents)
    return combined, {
        "sources_total": len(urls),
        "sources_loaded": sum(1 for item in source_results if item["loaded"]),
        "duplicate_payloads": duplicate_payloads,
        "unsupported_protocols": unsupported_protocols,
        "sources": source_results,
    }


def build_combined_provider_yaml():
    outline_yaml = None
    sub_yaml = None
    outline_entries = 0
    sub_entries = 0
    outline_error = None
    sub_error = None
    sub_details = {
        "sources_total": 0,
        "sources_loaded": 0,
        "duplicate_payloads": 0,
        "unsupported_protocols": {},
        "sources": [],
    }

    try:
        outline_yaml = load_outline_yaml()
        if outline_yaml:
            print("Loaded Outline access key configuration.", flush=True)
            outline_entries = len(
                [
                    line
                    for line in extract_proxy_entries(outline_yaml)
                    if line.startswith("  - name:")
                ]
            )
    except Exception as e:
        print(f"Outline config error: {e}.", flush=True)
        outline_error = str(e)

    try:
        sub_yaml, sub_details = load_subscription_yaml()
        if sub_yaml:
            print(
                "Loaded subscription configuration "
                f"from {sub_details['sources_loaded']}/{sub_details['sources_total']} sources.",
                flush=True,
            )
            sub_entries = len(
                [line for line in extract_proxy_entries(sub_yaml) if line.startswith("  - name:")]
            )
    except Exception as e:
        sub_error = _safe_fetch_error(e)
        print(f"Subscription config error: {sub_error}.", flush=True)

    merged_yaml = merge_proxy_yaml_documents(outline_yaml, sub_yaml)
    merged_entries = (
        0
        if not merged_yaml
        else len(
            [line for line in extract_proxy_entries(merged_yaml) if line.startswith("  - name:")]
        )
    )
    STATE["last_build"] = {
        "outline_loaded": bool(outline_yaml),
        "outline_entries": outline_entries,
        "outline_error": outline_error,
        "subscription_loaded": bool(sub_yaml),
        "subscription_entries": sub_entries,
        "subscription_error": sub_error,
        "subscription_sources_total": sub_details["sources_total"],
        "subscription_sources_loaded": sub_details["sources_loaded"],
        "subscription_duplicate_payloads": sub_details["duplicate_payloads"],
        "subscription_unsupported_protocols": sub_details["unsupported_protocols"],
        "subscription_sources": sub_details["sources"],
        "merged_entries": merged_entries,
    }

    return merged_yaml


def controller_request(path, *, method="GET", query=None, body=None):
    url = f"{CONTROLLER_URL.rstrip('/')}{path}"
    if query:
        url = f"{url}?{urlencode(query)}"

    request = urllib.request.Request(
        url,
        method=method,
        data=None if body is None else json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=10) as resp:
        raw = resp.read().decode("utf-8", errors="ignore")
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"raw": raw}


def build_controller_snapshot():
    snapshot = {"controller_url": CONTROLLER_URL}

    try:
        snapshot["providers"] = controller_request("/providers/proxies")
    except Exception as e:
        snapshot["providers_error"] = str(e)

    try:
        snapshot["telegram_group"] = controller_request("/group/TELEGRAM-AUTO")
    except Exception as e:
        snapshot["telegram_group_error"] = str(e)

    try:
        snapshot["openai_group"] = controller_request("/group/OPENAI-AUTO")
    except Exception as e:
        snapshot["openai_group_error"] = str(e)

    return snapshot


def _collect_named_proxy_records(obj, index):
    if isinstance(obj, dict):
        name = obj.get("name")
        if isinstance(name, str) and name.strip():
            index.setdefault(name, obj)
        for value in obj.values():
            _collect_named_proxy_records(value, index)
    elif isinstance(obj, list):
        for value in obj:
            _collect_named_proxy_records(value, index)


def _normalize_delay_value(record):
    if not isinstance(record, dict):
        return None

    for key in ("delay", "meanDelay", "mean_delay"):
        value = record.get(key)
        if isinstance(value, (int, float)):
            return value

    history = record.get("history")
    if isinstance(history, list):
        delays = [
            item.get("delay")
            for item in history
            if isinstance(item, dict) and isinstance(item.get("delay"), (int, float))
        ]
        if delays:
            return delays[-1]

    return None


def _build_group_summary(group_name, group_snapshot, proxy_index):
    if not isinstance(group_snapshot, dict):
        return {
            "group": group_name,
            "selected": None,
            "candidate_count": 0,
            "top_candidates": [],
        }

    candidate_names = []
    for key in ("all", "proxies"):
        values = group_snapshot.get(key)
        if isinstance(values, list):
            candidate_names.extend([value for value in values if isinstance(value, str)])

    seen = set()
    ordered_names = []
    for name in candidate_names:
        if name not in seen:
            ordered_names.append(name)
            seen.add(name)

    candidates = []
    for name in ordered_names:
        record = proxy_index.get(name, {})
        candidates.append(
            {
                "name": name,
                "alive": record.get("alive"),
                "delay": _normalize_delay_value(record),
            }
        )

    candidates.sort(
        key=lambda item: (
            item["delay"] is None,
            item["delay"] if item["delay"] is not None else float("inf"),
            item["name"],
        )
    )

    return {
        "group": group_name,
        "selected": group_snapshot.get("now") or group_snapshot.get("selected"),
        "candidate_count": len(ordered_names),
        "top_candidates": candidates[:5],
    }


def build_summary_payload():
    controller_snapshot = build_controller_snapshot()
    proxy_index = {}
    _collect_named_proxy_records(controller_snapshot, proxy_index)

    return {
        "state": STATE,
        "telegram": _build_group_summary(
            "TELEGRAM-AUTO",
            controller_snapshot.get("telegram_group"),
            proxy_index,
        ),
        "openai": _build_group_summary(
            "OPENAI-AUTO",
            controller_snapshot.get("openai_group"),
            proxy_index,
        ),
    }


def trigger_group_recheck(target):
    targets = []
    normalized = (target or "all").strip().lower()

    if normalized in {"telegram", "all"}:
        targets.append(
            {
                "provider": "something-telegram",
                "group": "TELEGRAM-AUTO",
                "url": "https://api.telegram.org",
            }
        )
    if normalized in {"openai", "all"}:
        targets.append(
            {
                "provider": "something-openai",
                "group": "OPENAI-AUTO",
                "url": "https://api.openai.com/v1/models",
            }
        )

    results = []
    for current in targets:
        entry = {"target": current["group"]}

        try:
            entry["provider_healthcheck"] = controller_request(
                f"/providers/proxies/{current['provider']}/healthcheck",
                method="PUT",
                query={"url": current["url"], "timeout": 7000},
            )
        except Exception as e:
            entry["provider_healthcheck_error"] = str(e)

        try:
            entry["group_delay"] = controller_request(
                f"/group/{current['group']}/delay",
                query={"url": current["url"], "timeout": 7000},
            )
        except Exception as e:
            entry["group_delay_error"] = str(e)

        results.append(entry)

    return {"requested_target": normalized, "results": results}


def _query_first(query, key, default=None):
    values = query.get(key)
    if not values:
        return default
    return values[0]


def _query_bool(query, *keys, default=False):
    for key in keys:
        value = _query_first(query, key)
        if value is None:
            continue
        return str(value).strip().lower() in {"1", "true", "yes", "on"}
    return default


def _split_list_value(value):
    if value is None:
        return []
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _safe_node_name(value, fallback, prefix):
    decoded = unquote(str(value or ""))
    cleaned = re.sub(r"[^\w\s().,+@-]", "", decoded).strip()
    return f"{prefix}-{cleaned or fallback}"


def _base_proxy_lines(name, proxy_type, parsed):
    if not parsed.hostname or parsed.port is None:
        return None
    return [
        f"  - name: {quote_yaml_scalar(name)}",
        f"    type: {proxy_type}",
        f"    server: {quote_yaml_scalar(parsed.hostname)}",
        f"    port: {parsed.port}",
    ]


def _append_xhttp_extra(lines, raw_extra):
    if isinstance(raw_extra, str):
        try:
            extra = json.loads(raw_extra)
        except (TypeError, ValueError):
            return
    else:
        extra = safe_dict(raw_extra)
    if not extra:
        return

    option_mapping = {
        "xPaddingBytes": "x-padding-bytes",
        "xPaddingObfsMode": "x-padding-obfs-mode",
        "xPaddingKey": "x-padding-key",
        "xPaddingHeader": "x-padding-header",
        "xPaddingPlacement": "x-padding-placement",
        "xPaddingMethod": "x-padding-method",
        "uplinkHTTPMethod": "uplink-http-method",
        "sessionPlacement": "session-placement",
        "sessionKey": "session-key",
        "seqPlacement": "seq-placement",
        "seqKey": "seq-key",
        "uplinkDataPlacement": "uplink-data-placement",
        "uplinkDataKey": "uplink-data-key",
        "uplinkChunkSize": "uplink-chunk-size",
        "scMaxEachPostBytes": "sc-max-each-post-bytes",
    }
    for source_key, target_key in option_mapping.items():
        append_yaml_field(lines, target_key, extra.get(source_key), indent="      ")

    xmux = safe_dict(extra.get("xmux"))
    if not xmux:
        return

    mapping = {
        "maxConcurrency": "max-concurrency",
        "maxConnections": "max-connections",
        "cMaxReuseTimes": "c-max-reuse-times",
        "hMaxRequestTimes": "h-max-request-times",
        "hMaxReusableSecs": "h-max-reusable-secs",
        "hKeepAlivePeriod": "h-keep-alive-period",
    }
    rendered = []
    for source_key, target_key in mapping.items():
        value = xmux.get(source_key)
        if value is not None and str(value).strip() != "":
            rendered.append((target_key, value))
    if not rendered:
        return
    lines.append("      reuse-settings:")
    for key, value in rendered:
        append_yaml_field(lines, key, value, indent="        ")


def _append_xhttp_reuse_settings(lines, query):
    _append_xhttp_extra(lines, _query_first(query, "extra"))


def _append_transport(lines, query, network):
    network = str(network or "tcp").strip().lower()
    if network == "httpupgrade":
        lines.append('    network: "ws"')
        lines.append("    ws-opts:")
        append_yaml_field(lines, "path", _query_first(query, "path", "/"), indent="      ")
        host = _query_first(query, "host")
        if host:
            lines.append("      headers:")
            append_yaml_field(lines, "Host", host, indent="        ")
        lines.append("      v2ray-http-upgrade: true")
        return

    append_yaml_field(lines, "network", network)
    if network == "ws":
        lines.append("    ws-opts:")
        append_yaml_field(lines, "path", _query_first(query, "path", "/"), indent="      ")
        host = _query_first(query, "host")
        if host:
            lines.append("      headers:")
            append_yaml_field(lines, "Host", host, indent="        ")
    elif network == "grpc":
        lines.append("    grpc-opts:")
        append_yaml_field(
            lines,
            "grpc-service-name",
            _query_first(query, "serviceName", ""),
            indent="      ",
        )
    elif network == "xhttp":
        lines.append("    xhttp-opts:")
        append_yaml_field(lines, "path", _query_first(query, "path", "/"), indent="      ")
        append_yaml_field(lines, "host", _query_first(query, "host"), indent="      ")
        append_yaml_field(lines, "mode", _query_first(query, "mode", "auto"), indent="      ")
        _append_xhttp_reuse_settings(lines, query)


def _append_tls_fields(lines, query, security):
    security = str(security or "").lower()
    if security not in {"tls", "reality"}:
        return
    lines.append("    tls: true")
    append_yaml_field(lines, "servername", _query_first(query, "sni"))
    append_yaml_field(lines, "client-fingerprint", _query_first(query, "fp"))
    append_yaml_field(
        lines,
        "skip-cert-verify",
        _query_bool(query, "insecure", "allowInsecure"),
    )
    append_yaml_list(lines, "alpn", _split_list_value(_query_first(query, "alpn")))
    if security == "reality":
        public_key = _query_first(query, "pbk")
        short_id = _query_first(query, "sid")
        if public_key or short_id:
            lines.append("    reality-opts:")
            append_yaml_field(lines, "public-key", public_key, indent="      ")
            append_yaml_field(lines, "short-id", short_id, indent="      ")


def _parse_ss_uri(parsed, name):
    userinfo = parsed.netloc.rsplit("@", 1)[0]
    method = unquote(parsed.username or "")
    password = unquote(parsed.password or "")
    if not password:
        try:
            method, password = _decode_base64_urlsafe(unquote(userinfo)).split(":", 1)
        except (ValueError, UnicodeDecodeError):
            return None
    lines = _base_proxy_lines(name, "ss", parsed)
    if not lines or not method or not password:
        return None
    append_yaml_field(lines, "cipher", method)
    append_yaml_field(lines, "password", password)
    lines.append("    udp: true")

    query = parse_qs(parsed.query, keep_blank_values=True)
    plugin_value = _query_first(query, "plugin")
    if plugin_value:
        parts = [part for part in plugin_value.split(";") if part]
        plugin = parts[0]
        opts = {}
        for part in parts[1:]:
            if "=" in part:
                key, value = part.split("=", 1)
                opts[key] = value
            else:
                opts[part] = True
        append_yaml_field(lines, "plugin", plugin)
        if opts:
            lines.append("    plugin-opts:")
            for key, value in opts.items():
                if key.lower() == "mux" and str(value).lower() in {
                    "0",
                    "1",
                    "false",
                    "true",
                }:
                    value = str(value).lower() in {"1", "true"}
                append_yaml_field(lines, key, value, indent="      ")
    return lines


def _parse_vmess_uri(uri, name):
    payload = uri.split("://", 1)[1].split("#", 1)[0]
    try:
        config = json.loads(_decode_base64_urlsafe(payload))
        server = config.get("add")
        port = int(config.get("port"))
        uuid = config.get("id")
    except (TypeError, ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not server or not port or not uuid:
        return None
    lines = [
        f"  - name: {quote_yaml_scalar(name)}",
        "    type: vmess",
        f"    server: {quote_yaml_scalar(server)}",
        f"    port: {port}",
    ]
    append_yaml_field(lines, "uuid", uuid)
    append_yaml_field(lines, "alterId", config.get("aid", 0))
    append_yaml_field(lines, "cipher", config.get("scy") or "auto")
    lines.append("    udp: true")
    query = {
        "path": [config.get("path", "")],
        "host": [config.get("host", "")],
        "serviceName": [config.get("path", "")],
    }
    _append_transport(lines, query, config.get("net", "tcp"))
    if str(config.get("tls", "")).lower() in {"tls", "1", "true"}:
        lines.append("    tls: true")
        append_yaml_field(lines, "servername", config.get("sni") or config.get("host"))
        append_yaml_field(lines, "client-fingerprint", config.get("fp"))
        append_yaml_list(lines, "alpn", _split_list_value(config.get("alpn")))
    return lines


def _parse_uri_node(uri, *, name_prefix, node_index):
    scheme = uri.split("://", 1)[0].lower()
    fragment = uri.rsplit("#", 1)[1] if "#" in uri else ""
    name = _safe_node_name(
        fragment,
        scheme,
        f"{name_prefix}-{node_index}",
    )
    if scheme == "vmess":
        return _parse_vmess_uri(uri, name)

    try:
        parsed = urlsplit(uri)
        query = parse_qs(parsed.query, keep_blank_values=True)
    except ValueError:
        return None

    if scheme == "ss":
        return _parse_ss_uri(parsed, name)

    if scheme in {"vless", "trojan"}:
        lines = _base_proxy_lines(name, scheme, parsed)
        credential = unquote(parsed.username or "")
        if not lines or not credential:
            return None
        append_yaml_field(lines, "uuid" if scheme == "vless" else "password", credential)
        if scheme == "vless":
            append_yaml_field(lines, "flow", _query_first(query, "flow"))
            append_yaml_field(lines, "encryption", _query_first(query, "encryption"))
        lines.append("    udp: true")
        _append_transport(lines, query, _query_first(query, "type", "tcp"))
        _append_tls_fields(lines, query, _query_first(query, "security"))
        return lines

    if scheme in {"hysteria2", "hy2"}:
        lines = _base_proxy_lines(name, "hysteria2", parsed)
        password = unquote(parsed.password or parsed.username or "")
        if not lines or not password:
            return None
        append_yaml_field(lines, "password", password)
        append_yaml_field(lines, "sni", _query_first(query, "sni"))
        append_yaml_field(lines, "skip-cert-verify", _query_bool(query, "insecure"))
        append_yaml_field(lines, "obfs", _query_first(query, "obfs"))
        append_yaml_field(lines, "obfs-password", _query_first(query, "obfs-password"))
        append_yaml_list(lines, "alpn", _split_list_value(_query_first(query, "alpn")))
        return lines

    if scheme == "tuic":
        lines = _base_proxy_lines(name, "tuic", parsed)
        uuid = unquote(parsed.username or "")
        password = unquote(parsed.password or "")
        if not lines or not uuid or not password:
            return None
        append_yaml_field(lines, "uuid", uuid)
        append_yaml_field(lines, "password", password)
        append_yaml_field(lines, "sni", _query_first(query, "sni"))
        append_yaml_field(lines, "udp-relay-mode", _query_first(query, "udp_relay_mode"))
        append_yaml_field(
            lines,
            "congestion-controller",
            _query_first(query, "congestion_control"),
        )
        append_yaml_field(lines, "skip-cert-verify", _query_bool(query, "insecure"))
        append_yaml_list(lines, "alpn", _split_list_value(_query_first(query, "alpn")))
        return lines

    if scheme == "anytls":
        lines = _base_proxy_lines(name, "anytls", parsed)
        password = unquote(parsed.password or parsed.username or "")
        if not lines or not password:
            return None
        append_yaml_field(lines, "password", password)
        append_yaml_field(lines, "sni", _query_first(query, "sni"))
        append_yaml_field(lines, "client-fingerprint", _query_first(query, "fp") or "chrome")
        append_yaml_field(lines, "skip-cert-verify", _query_bool(query, "insecure"))
        lines.append("    udp: true")
        return lines

    if scheme == "hysteria":
        lines = _base_proxy_lines(name, "hysteria", parsed)
        auth = _query_first(query, "auth") or _query_first(query, "auth_str")
        if not lines or not auth:
            return None
        append_yaml_field(lines, "auth-str", auth)
        append_yaml_field(lines, "protocol", _query_first(query, "protocol", "udp"))
        append_yaml_field(lines, "up", _query_first(query, "upmbps"))
        append_yaml_field(lines, "down", _query_first(query, "downmbps"))
        append_yaml_field(
            lines,
            "obfs",
            _query_first(query, "obfsParam") or _query_first(query, "obfs"),
        )
        append_yaml_field(lines, "sni", _query_first(query, "peer"))
        append_yaml_field(lines, "skip-cert-verify", _query_bool(query, "insecure"))
        append_yaml_list(lines, "alpn", _split_list_value(_query_first(query, "alpn")))
        return lines

    if scheme == "mierus":
        port_value = _query_first(query, "port")
        try:
            port = parsed.port or int(port_value)
        except (TypeError, ValueError):
            return None
        if not parsed.hostname or not parsed.username or not parsed.password:
            return None
        lines = [
            f"  - name: {quote_yaml_scalar(name)}",
            "    type: mieru",
            f"    server: {quote_yaml_scalar(parsed.hostname)}",
            f"    port: {port}",
        ]
        append_yaml_field(lines, "username", unquote(parsed.username))
        append_yaml_field(lines, "password", unquote(parsed.password))
        append_yaml_field(lines, "transport", _query_first(query, "protocol", "TCP"))
        append_yaml_field(lines, "multiplexing", _query_first(query, "multiplexing"))
        append_yaml_field(lines, "handshake-mode", _query_first(query, "handshake-mode"))
        return lines

    return None


def process_uri_subscription(raw_data, *, name_prefix="sub"):
    text = str(raw_data or "").strip()
    compact = "".join(text.split())
    if "://" not in text and compact:
        try:
            decoded = _decode_base64_urlsafe(compact)
            if "://" in decoded:
                text = decoded
        except (ValueError, UnicodeDecodeError):
            pass

    yaml_lines = ["proxies:"]
    unsupported = {}
    seen_uris = set()
    valid_nodes = 0
    for line in text.splitlines():
        uri = line.strip()
        if not uri or "://" not in uri or uri in seen_uris:
            continue
        seen_uris.add(uri)
        scheme = uri.split("://", 1)[0].lower()
        node_lines = _parse_uri_node(
            uri,
            name_prefix=name_prefix,
            node_index=valid_nodes + 1,
        )
        if not node_lines:
            unsupported[scheme] = unsupported.get(scheme, 0) + 1
            continue
        yaml_lines.extend(node_lines)
        valid_nodes += 1
    return ("\n".join(yaml_lines) if valid_nodes else None), {
        "unsupported_protocols": unsupported,
        "valid_nodes": valid_nodes,
    }


def process_subscription_payload(raw_data, *, name_prefix="sub"):
    text = str(raw_data or "").strip()
    if not text:
        return None, {"unsupported_protocols": {}, "valid_nodes": 0}

    try:
        parsed_json = json.loads(text)
    except (TypeError, ValueError):
        parsed_json = None
    if isinstance(parsed_json, (dict, list)):
        rendered = process_something_json(text, name_prefix=name_prefix)
        count = len(
            [line for line in extract_proxy_entries(rendered) if line.startswith("  - name:")]
        )
        return rendered, {"unsupported_protocols": {}, "valid_nodes": count}

    if re.search(r"(?m)^\s*proxies\s*:", text):
        normalized_text = normalize_legacy_ss_plugin_yaml(replace_json_surrogate_pairs(text))
        count = len(
            [
                line
                for line in extract_proxy_entries(normalized_text)
                if line.startswith("  - name:")
            ]
        )
        return normalized_text, {"unsupported_protocols": {}, "valid_nodes": count}

    return process_uri_subscription(text, name_prefix=name_prefix)


def _render_happ_socks(outbound, name):
    settings = safe_dict(outbound.get("settings"))
    servers = safe_list(settings.get("servers"))
    if not servers:
        return None
    server = safe_dict(servers[0])
    if not server.get("address"):
        return None
    lines = [
        f"  - name: {quote_yaml_scalar(name)}",
        "    type: socks5",
        f"    server: {quote_yaml_scalar(server.get('address'))}",
        f"    port: {server.get('port', 1080)}",
    ]
    users = safe_list(server.get("users"))
    user = safe_dict(users[0]) if users else {}
    append_yaml_field(lines, "username", user.get("user"))
    append_yaml_field(lines, "password", user.get("pass"))
    return lines


def _render_happ_vless(outbound, name, tag_names, fallback_dialer=None):
    settings = safe_dict(outbound.get("settings"))
    servers = safe_list(settings.get("vnext"))
    if not servers:
        return None
    server = safe_dict(servers[0])
    users = safe_list(server.get("users"))
    user = safe_dict(users[0]) if users else {}
    if not server.get("address") or not user.get("id"):
        return None

    stream = safe_dict(outbound.get("streamSettings"))
    tls_settings = safe_dict(stream.get("tlsSettings"))
    reality = safe_dict(stream.get("realitySettings"))
    sockopt = safe_dict(stream.get("sockopt"))
    network = str(stream.get("network", "tcp") or "tcp").lower()
    security = str(stream.get("security", "") or "").lower()
    server_name = (
        reality.get("serverName")
        or tls_settings.get("serverName")
        or tls_settings.get("sni")
        or server.get("address")
    )
    client_fingerprint = reality.get("fingerprint") or tls_settings.get("fingerprint") or "chrome"
    packet_encoding = (
        user.get("packetEncoding")
        or settings.get("packetEncoding")
        or stream.get("packetEncoding")
        or ("xudp" if user.get("flow") == "xtls-rprx-vision" else None)
    )
    encryption = user.get("encryption")

    lines = [
        f"  - name: {quote_yaml_scalar(name)}",
        "    type: vless",
        f"    server: {quote_yaml_scalar(server.get('address'))}",
        f"    port: {server.get('port', 443)}",
        f"    uuid: {quote_yaml_scalar(user.get('id'))}",
        f"    network: {quote_yaml_scalar(network)}",
        "    udp: true",
    ]
    if network == "ws":
        ws_settings = safe_dict(stream.get("wsSettings"))
        lines.append("    ws-opts:")
        append_yaml_field(lines, "path", ws_settings.get("path", "/"), indent="      ")
        headers = safe_dict(ws_settings.get("headers"))
        if headers:
            lines.append("      headers:")
            for key, value in headers.items():
                append_yaml_field(lines, key, value, indent="        ")
    elif network == "grpc":
        grpc_settings = safe_dict(stream.get("grpcSettings"))
        lines.append("    grpc-opts:")
        append_yaml_field(
            lines,
            "grpc-service-name",
            grpc_settings.get("serviceName", ""),
            indent="      ",
        )
    elif network == "xhttp":
        xhttp_settings = safe_dict(stream.get("xhttpSettings"))
        lines.append("    xhttp-opts:")
        append_yaml_field(lines, "path", xhttp_settings.get("path", "/"), indent="      ")
        append_yaml_field(lines, "host", xhttp_settings.get("host"), indent="      ")
        append_yaml_field(lines, "mode", xhttp_settings.get("mode", "auto"), indent="      ")
        _append_xhttp_extra(lines, xhttp_settings.get("extra"))

    if security in {"tls", "reality"}:
        lines.append("    tls: true")
        append_yaml_field(
            lines,
            "skip-cert-verify",
            bool(tls_settings.get("allowInsecure", False)),
        )

    append_yaml_field(lines, "flow", user.get("flow"))
    append_yaml_field(lines, "packet-encoding", packet_encoding)
    append_yaml_field(lines, "servername", server_name)
    append_yaml_field(lines, "client-fingerprint", client_fingerprint)
    append_yaml_list(lines, "alpn", tls_settings.get("alpn"))
    append_yaml_field(lines, "encryption", encryption)

    public_key = reality.get("publicKey")
    short_id = str(reality.get("shortId", ""))
    valid_short_id = short_id and all(char in "0123456789abcdefABCDEF" for char in short_id)
    if public_key or valid_short_id:
        lines.append("    reality-opts:")
        append_yaml_field(lines, "public-key", public_key, indent="      ")
        if encryption and "mlkem768" in str(encryption).lower():
            lines.append("      support-x25519mlkem768: true")
        if valid_short_id:
            append_yaml_field(lines, "short-id", short_id, indent="      ")

    dialer_tag = sockopt.get("dialerProxy")
    dialer_name = tag_names.get(str(dialer_tag)) if dialer_tag else fallback_dialer
    append_yaml_field(lines, "dialer-proxy", dialer_name)
    return lines


def _render_happ_hysteria2(outbound, name):
    settings = safe_dict(outbound.get("settings"))
    stream = safe_dict(outbound.get("streamSettings"))
    hysteria_settings = safe_dict(stream.get("hysteriaSettings"))
    tls_settings = safe_dict(stream.get("tlsSettings"))
    if not settings.get("address") or not hysteria_settings.get("auth"):
        return None
    lines = [
        f"  - name: {quote_yaml_scalar(name)}",
        "    type: hysteria2",
        f"    server: {quote_yaml_scalar(settings.get('address'))}",
        f"    port: {settings.get('port', 443)}",
    ]
    append_yaml_field(lines, "password", hysteria_settings.get("auth"))
    append_yaml_field(lines, "sni", tls_settings.get("serverName"))
    append_yaml_field(
        lines,
        "skip-cert-verify",
        bool(tls_settings.get("allowInsecure", False)),
    )
    append_yaml_list(lines, "alpn", tls_settings.get("alpn"))
    return lines


def _render_happ_shadowsocks(outbound, base_name):
    settings = safe_dict(outbound.get("settings"))
    rendered = []
    for server_index, server_value in enumerate(safe_list(settings.get("servers")), start=1):
        server = safe_dict(server_value)
        if not all(server.get(key) for key in ("address", "port", "method", "password")):
            continue
        name = f"{base_name}-{server_index}"
        lines = [
            f"  - name: {quote_yaml_scalar(name)}",
            "    type: ss",
            f"    server: {quote_yaml_scalar(server.get('address'))}",
            f"    port: {server.get('port')}",
        ]
        append_yaml_field(lines, "cipher", server.get("method"))
        append_yaml_field(lines, "password", server.get("password"))
        lines.append("    udp: true")
        if server.get("uot"):
            lines.append("    udp-over-tcp: true")
            append_yaml_field(lines, "udp-over-tcp-version", server.get("UoTVersion", 1))
        rendered.append(lines)
    return rendered


def process_something_json(raw_data, *, name_prefix="json"):
    try:
        configs = json.loads(raw_data)
        if isinstance(configs, dict):
            configs = [configs]
        if not isinstance(configs, list):
            return None
    except Exception as exc:
        print(f"JSON Parse Error: {exc}", flush=True)
        return None

    yaml_lines = ["proxies:"]
    valid_nodes = 0
    for config_index, config_value in enumerate(configs):
        config = safe_dict(config_value)
        outbounds = [safe_dict(item) for item in safe_list(config.get("outbounds"))]
        raw_name = config.get("remarks", f"Node_{config_index}")
        tag_names = {}
        named_outbounds = []
        for outbound_index, outbound in enumerate(outbounds):
            protocol = str(outbound.get("protocol", "")).lower()
            if protocol not in {"socks", "vless", "hysteria", "shadowsocks"}:
                continue
            name_value = outbound.get("tag") if protocol == "socks" else raw_name
            name = _safe_node_name(
                name_value,
                f"{protocol}-{config_index}-{outbound_index}",
                f"{name_prefix}-{config_index}-{outbound_index}",
            )
            named_outbounds.append((protocol, outbound, name))
            if outbound.get("tag"):
                tag_names[str(outbound.get("tag"))] = name

        socks_names = []
        for protocol, outbound, name in named_outbounds:
            if protocol != "socks":
                continue
            rendered = _render_happ_socks(outbound, name)
            if rendered:
                yaml_lines.extend(rendered)
                socks_names.append(name)
                valid_nodes += 1

        fallback_dialer = socks_names[0] if len(socks_names) == 1 else None
        for protocol, outbound, name in named_outbounds:
            if protocol == "vless":
                rendered = _render_happ_vless(
                    outbound,
                    name,
                    tag_names,
                    fallback_dialer=fallback_dialer,
                )
                rendered_nodes = [rendered] if rendered else []
            elif protocol == "hysteria":
                rendered = _render_happ_hysteria2(outbound, name)
                rendered_nodes = [rendered] if rendered else []
            elif protocol == "shadowsocks":
                rendered_nodes = _render_happ_shadowsocks(outbound, name)
            else:
                continue

            for rendered in rendered_nodes:
                yaml_lines.extend(rendered)
                valid_nodes += 1

    return "\n".join(yaml_lines) if valid_nodes > 0 else None


def read_cached_provider_yaml():
    if not os.path.exists(CACHE_FILE):
        return None
    with CACHE_LOCK:
        try:
            with open(CACHE_FILE, encoding="utf-8") as cache_file:
                return cache_file.read()
        except FileNotFoundError:
            return None


def write_cached_provider_yaml(yaml_text):
    cache_dir = os.path.dirname(CACHE_FILE)
    os.makedirs(cache_dir, exist_ok=True)
    temp_path = f"{CACHE_FILE}.tmp-{os.getpid()}-{threading.get_ident()}"
    with CACHE_LOCK:
        try:
            with open(temp_path, "w", encoding="utf-8") as cache_file:
                os.chmod(temp_path, 0o600)
                cache_file.write(yaml_text)
                cache_file.flush()
                os.fsync(cache_file.fileno())
            os.replace(temp_path, CACHE_FILE)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
    STATE["last_cache_write"] = {"cache_file": CACHE_FILE}


def cache_needs_refresh():
    try:
        age = time.time() - os.path.getmtime(CACHE_FILE)
    except OSError:
        return True
    return age >= CACHE_REFRESH_INTERVAL_SECONDS


def build_and_cache_provider_yaml():
    yaml_out = build_combined_provider_yaml()
    if yaml_out:
        write_cached_provider_yaml(yaml_out)
        print("Success! Cache updated.", flush=True)
    return yaml_out


def load_or_build_provider_yaml():
    cached = read_cached_provider_yaml()
    if cached:
        if cache_needs_refresh():
            start_background_refresh()
        return cached

    with BUILD_LOCK:
        cached = read_cached_provider_yaml()
        if cached:
            return cached
        try:
            return build_and_cache_provider_yaml()
        except Exception as exc:
            print(f"Network error: {_safe_fetch_error(exc)}.", flush=True)
            return None


def reload_mihomo_providers():
    pending = {"something-telegram", "something-openai"}
    for _attempt in range(10):
        for provider in list(pending):
            try:
                controller_request(f"/providers/proxies/{provider}", method="PUT")
                pending.remove(provider)
            except Exception:
                pass
        if not pending:
            return
        time.sleep(1)
    if pending:
        print("Provider cache refreshed; Mihomo reload remains pending.", flush=True)


def refresh_provider_cache():
    STATE["refresh"] = {"running": True, "error": None}
    try:
        with BUILD_LOCK:
            yaml_out = build_and_cache_provider_yaml()
        if yaml_out:
            reload_mihomo_providers()
        STATE["refresh"] = {"running": False, "error": None}
    except Exception as exc:
        safe_error = _safe_fetch_error(exc)
        STATE["refresh"] = {"running": False, "error": safe_error}
        print(f"Background subscription refresh error: {safe_error}.", flush=True)


def start_background_refresh():
    global REFRESH_THREAD

    with REFRESH_THREAD_LOCK:
        if REFRESH_THREAD is not None and REFRESH_THREAD.is_alive():
            return False
        REFRESH_THREAD = threading.Thread(
            target=refresh_provider_cache,
            name="subscription-refresh",
            daemon=True,
        )
        REFRESH_THREAD.start()
        return True


class SubHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path.startswith("/health"):
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True}).encode("utf-8"))
            return

        if self.path.startswith("/diagnostics"):
            payload = {
                "state": STATE,
                "cache_exists": os.path.exists(CACHE_FILE),
                "controller": build_controller_snapshot(),
            }
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode("utf-8"))
            return

        if self.path.startswith("/summary"):
            payload = build_summary_payload()
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode("utf-8"))
            return

        if self.path.startswith("/recheck"):
            parsed = urlsplit(self.path)
            target = parse_qs(parsed.query).get("group", ["all"])[0]
            payload = trigger_group_recheck(target)
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode("utf-8"))
            return

        yaml_out = load_or_build_provider_yaml()

        if yaml_out:
            self.send_response(200)
            self.send_header("Content-type", "application/yaml")
            self.end_headers()
            self.wfile.write(yaml_out.encode("utf-8"))
        else:
            self.send_response(500)
            self.end_headers()


def main():
    print("Cleaner with caching started on 8080", flush=True)
    start_background_refresh()
    ThreadingHTTPServer((PROXY_HTTP_BIND, 8080), SubHandler).serve_forever()


if __name__ == "__main__":
    main()
