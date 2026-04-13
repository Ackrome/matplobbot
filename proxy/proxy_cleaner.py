import json
import os
import re
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

CACHE_FILE = "/app/cache/last_good_sub.yaml"


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
        value_str = str(value).strip()
        if not value_str:
            return
        rendered = f"'{value_str}'"

    lines.append(f"{indent}{key}: {rendered}")


def append_yaml_list(lines, key, values, indent="    "):
    cleaned = [str(value).strip() for value in safe_list(values) if str(value).strip()]
    if not cleaned:
        return

    lines.append(f"{indent}{key}:")
    for value in cleaned:
        lines.append(f"{indent}- {value}")


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
                        f"  - name: '{socks_name}'\n    type: socks5\n    server: '{s_srv.get('address')}'\n    port: {s_srv.get('port', 1080)}"
                    )
                    if s_usr.get("user"):
                        yaml_lines.append(
                            f"    username: '{s_usr.get('user')}'\n    password: '{s_usr.get('pass')}'"
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
                reality.get("fingerprint")
                or tls_settings.get("fingerprint")
                or "chrome"
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
                f"  - name: '{safe_name}'",
                "    type: vless",
                f"    server: '{v_srv.get('address')}'",
                f"    port: {v_srv.get('port', 443)}",
                f"    uuid: '{v_usr.get('id')}'",
                f"    network: '{network}'",
                "    udp: true",
            ]

            if security in {"tls", "reality"}:
                proxy_lines.append("    tls: true")

            if v_usr.get("flow"):
                proxy_lines.append(f"    flow: '{v_usr.get('flow')}'")
            append_yaml_field(proxy_lines, "packet-encoding", packet_encoding)
            append_yaml_field(proxy_lines, "servername", server_name)
            append_yaml_field(proxy_lines, "client-fingerprint", client_fingerprint)
            append_yaml_field(proxy_lines, "skip-cert-verify", skip_cert_verify)
            append_yaml_list(proxy_lines, "alpn", tls_settings.get("alpn"))
            append_yaml_field(proxy_lines, "encryption", encryption)

            public_key = reality.get("publicKey")
            if public_key:
                proxy_lines.append("    reality-opts:")
                proxy_lines.append(f"      public-key: '{public_key}'")
                if encryption and "mlkem768" in str(encryption).lower():
                    proxy_lines.append("      support-x25519mlkem768: true")

            sid = str(reality.get("shortId", ""))
            if sid and all(c in "0123456789abcdefABCDEF" for c in sid):
                if not public_key:
                    proxy_lines.append("    reality-opts:")
                proxy_lines.append(f"      short-id: '{sid}'")

            dialer_proxy = sockopt.get("dialerProxy")
            if dialer_proxy:
                proxy_lines.append(f"    dialer-proxy: '{dialer_proxy}'")
            elif has_socks:
                proxy_lines.append(f"    dialer-proxy: '{socks_name}'")

            yaml_lines.extend(proxy_lines)
            valid_nodes += 1
        except:
            continue
    return "\n".join(yaml_lines) if valid_nodes > 0 else None


class SubHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        url = os.environ.get("SUB_URL")
        yaml_out = None
        try:
            print("Fetching subscription from somethingsomething...", flush=True)
            req = urllib.request.Request(url, headers={"User-Agent": "v2rayNG/1.8.5"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read().decode("utf-8", errors="ignore").strip()
                yaml_out = process_something_json(raw)
                if yaml_out:
                    with open(CACHE_FILE, "w") as f:
                        f.write(yaml_out)
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
    HTTPServer(("127.0.0.1", 8080), SubHandler).serve_forever()


if __name__ == "__main__":
    main()
