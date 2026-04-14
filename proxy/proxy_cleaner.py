import base64
import json
import os
import re
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

CACHE_FILE = "/app/cache/last_good_sub.yaml"
CONTROLLER_URL = os.environ.get("MIHOMO_CONTROLLER_URL", "http://127.0.0.1:9090")
PROXY_HTTP_BIND = os.environ.get("PROXY_HTTP_BIND", "0.0.0.0")

STATE = {
    "last_build": None,
    "last_cache_write": None,
}


def safe_dict(d):
    return d if isinstance(d, dict) else {}


def safe_list(l):
    return l if isinstance(l, list) else []


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
        rendered = json.dumps(value_str)

    lines.append(f"{indent}{key}: {rendered}")


def append_yaml_list(lines, key, values, indent="    "):
    cleaned = [str(value) for value in safe_list(values) if str(value).strip()]
    if not cleaned:
        return

    lines.append(f"{indent}{key}:")
    for value in cleaned:
        lines.append(f"{indent}- {json.dumps(value)}")


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
        f"  - name: {json.dumps(str(name))}",
        "    type: ss",
        f"    server: {json.dumps(str(server))}",
        f"    port: {port}",
        f"    cipher: {json.dumps(str(method))}",
        f"    password: {json.dumps(str(password))}",
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


def load_subscription_yaml():
    url = os.environ.get("SUB_URL")
    if not url:
        return None

    print("Fetching subscription from somethingsomething...", flush=True)
    req = urllib.request.Request(url, headers={"User-Agent": "v2rayNG/1.8.5"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        raw = resp.read().decode("utf-8", errors="ignore").strip()
    return process_something_json(raw)


def build_combined_provider_yaml():
    outline_yaml = None
    sub_yaml = None
    outline_entries = 0
    sub_entries = 0
    outline_error = None
    sub_error = None

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
        sub_yaml = load_subscription_yaml()
        if sub_yaml:
            print("Loaded subscription configuration.", flush=True)
            sub_entries = len(
                [line for line in extract_proxy_entries(sub_yaml) if line.startswith("  - name:")]
            )
    except Exception as e:
        print(f"Subscription config error: {e}.", flush=True)
        sub_error = str(e)

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


def process_something_json(raw_data):
    try:
        configs = json.loads(raw_data)
        if isinstance(configs, dict):
            configs = [configs]
        if not isinstance(configs, list):
            return None
    except Exception as e:
        print(f"JSON Parse Error: {e}", flush=True)
        return None

    yaml_lines = ["proxies:"]
    valid_nodes = 0
    for i, conf in enumerate(configs):
        conf = safe_dict(conf)
        raw_name = conf.get("remarks", f"Node_{i}")
        safe_name = re.sub(r"[^\w\s-]", "", str(raw_name)).strip()
        safe_name = f"{safe_name or 'something'}_{i}"

        vless = None
        socks = None
        for outbound in safe_list(conf.get("outbounds")):
            o = safe_dict(outbound)
            if o.get("protocol") == "vless":
                vless = o
            elif o.get("protocol") == "socks":
                socks = o

        if not vless:
            continue

        socks_name = f"socks_in_{i}"
        has_socks = False
        if socks:
            try:
                socks_name = str(socks.get("tag") or socks_name)
                s_sett = safe_dict(socks.get("settings"))
                s_srv = safe_dict(safe_list(s_sett.get("servers"))[0])
                s_usr = safe_dict(safe_list(s_srv.get("users"))[0])
                if s_srv.get("address"):
                    yaml_lines.append(
                        f"  - name: {json.dumps(str(socks_name))}\n    type: socks5\n    server: {json.dumps(str(s_srv.get('address')))}\n    port: {s_srv.get('port', 1080)}"
                    )
                    if s_usr.get("user"):
                        yaml_lines.append(
                            f"    username: {json.dumps(str(s_usr.get('user')))}\n    password: {json.dumps(str(s_usr.get('pass')))}"
                        )
                    has_socks = True
            except:
                pass

        try:
            v_sett = safe_dict(vless.get("settings"))
            v_srv = safe_dict(safe_list(v_sett.get("vnext"))[0])
            v_usr = safe_dict(safe_list(v_srv.get("users"))[0])
            stream = safe_dict(vless.get("streamSettings"))
            tls_settings = safe_dict(stream.get("tlsSettings"))
            reality = safe_dict(stream.get("realitySettings"))
            sockopt = safe_dict(stream.get("sockopt"))
            network = str(stream.get("network", "tcp") or "tcp")
            security = str(stream.get("security", "") or "").lower()

            server_name = (
                reality.get("serverName")
                or tls_settings.get("serverName")
                or tls_settings.get("sni")
                or v_srv.get("address")
            )
            client_fingerprint = (
                reality.get("fingerprint") or tls_settings.get("fingerprint") or "chrome"
            )
            packet_encoding = (
                v_usr.get("packetEncoding")
                or v_sett.get("packetEncoding")
                or stream.get("packetEncoding")
                or ("xudp" if v_usr.get("flow") == "xtls-rprx-vision" else None)
            )
            encryption = v_usr.get("encryption")
            skip_cert_verify = tls_settings.get("allowInsecure")
            if skip_cert_verify is None and security in {"tls", "reality"}:
                skip_cert_verify = True

            if not v_srv.get("address"):
                continue

            proxy_lines = [
                f"  - name: {json.dumps(str(safe_name))}",
                "    type: vless",
                f"    server: {json.dumps(str(v_srv.get('address')))}",
                f"    port: {v_srv.get('port', 443)}",
                f"    uuid: {json.dumps(str(v_usr.get('id')))}",
                f"    network: {json.dumps(str(network))}",
                "    udp: true",
            ]
            if network == "ws":
                ws_settings = safe_dict(stream.get("wsSettings"))
                proxy_lines.append("    ws-opts:")
                proxy_lines.append(f"      path: {json.dumps(str(ws_settings.get('path', '/')))}")
                headers = safe_dict(ws_settings.get("headers"))
                if headers:
                    proxy_lines.append("      headers:")
                    for k, v in headers.items():
                        proxy_lines.append(f"        {k}: {json.dumps(str(v))}")
            elif network == "grpc":
                grpc_settings = safe_dict(stream.get("grpcSettings"))
                proxy_lines.append("    grpc-opts:")
                proxy_lines.append(
                    f"      grpc-service-name: {json.dumps(str(grpc_settings.get('serviceName', '')))}"
                )

            if security in {"tls", "reality"}:
                proxy_lines.append("    tls: true")

            if v_usr.get("flow"):
                proxy_lines.append(f"    flow: {json.dumps(str(v_usr.get('flow')))}")
            append_yaml_field(proxy_lines, "packet-encoding", packet_encoding)
            append_yaml_field(proxy_lines, "servername", server_name)
            append_yaml_field(proxy_lines, "client-fingerprint", client_fingerprint)
            append_yaml_field(proxy_lines, "skip-cert-verify", skip_cert_verify)
            append_yaml_list(proxy_lines, "alpn", tls_settings.get("alpn"))
            append_yaml_field(proxy_lines, "encryption", encryption)

            public_key = reality.get("publicKey")
            if public_key:
                proxy_lines.append("    reality-opts:")
                proxy_lines.append(f"      public-key: {json.dumps(str(public_key))}")
                if encryption and "mlkem768" in str(encryption).lower():
                    proxy_lines.append("      support-x25519mlkem768: true")

            sid = str(reality.get("shortId", ""))
            if sid and all(c in "0123456789abcdefABCDEF" for c in sid):
                if not public_key:
                    proxy_lines.append("    reality-opts:")
                proxy_lines.append(f"      short-id: {json.dumps(sid)}")

            dialer_proxy = sockopt.get("dialerProxy")
            if dialer_proxy:
                proxy_lines.append(f"    dialer-proxy: {json.dumps(str(dialer_proxy))}")
            elif has_socks:
                proxy_lines.append(f"    dialer-proxy: {json.dumps(str(socks_name))}")

            yaml_lines.extend(proxy_lines)
            valid_nodes += 1
        except:
            continue
    return "\n".join(yaml_lines) if valid_nodes > 0 else None


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

        yaml_out = None

        try:
            yaml_out = build_combined_provider_yaml()
            if yaml_out:
                with open(CACHE_FILE, "w") as f:
                    f.write(yaml_out)
                STATE["last_cache_write"] = {"cache_file": CACHE_FILE}
                print("Success! Cache updated.", flush=True)
        except Exception as e:
            print(f"Network error: {e}. Trying to load from cache...", flush=True)

        if not yaml_out and os.path.exists(CACHE_FILE):
            with open(CACHE_FILE) as f:
                yaml_out = f.read()
            print("Serving from disk cache.", flush=True)

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
    HTTPServer((PROXY_HTTP_BIND, 8080), SubHandler).serve_forever()


if __name__ == "__main__":
    main()
