import urllib.request, json, os, base64, re, sys
from http.server import BaseHTTPRequestHandler, HTTPServer

CACHE_FILE = "/app/cache/last_good_sub.yaml"

def safe_dict(d): return d if isinstance(d, dict) else {}
def safe_list(l): return l if isinstance(l, list) else []

def process_something_json(raw_data):
    try:
        configs = json.loads(raw_data)
        if isinstance(configs, dict): configs = [configs]
        if not isinstance(configs, list): return None
    except Exception as e:
        print(f"JSON Parse Error: {e}", flush=True)
        return None

    yaml_lines = ["proxies:"]
    valid_nodes = 0
    for i, conf in enumerate(configs):
        conf = safe_dict(conf)
        raw_name = conf.get('remarks', f'Node_{i}')
        safe_name = re.sub(r'[^\w\s-]', '', str(raw_name)).strip()
        safe_name = f"{safe_name or 'something'}_{i}"
        
        vless = None
        socks = None
        for outbound in safe_list(conf.get('outbounds')):
            o = safe_dict(outbound)
            if o.get('protocol') == 'vless': vless = o
            elif o.get('protocol') == 'socks': socks = o
        
        if not vless: continue
        
        socks_name = f"socks_in_{i}"
        has_socks = False
        if socks:
            try:
                s_sett = safe_dict(socks.get('settings'))
                s_srv = safe_dict(safe_list(s_sett.get('servers'))[0])
                s_usr = safe_dict(safe_list(s_srv.get('users'))[0])
                if s_srv.get('address'):
                    yaml_lines.append(f"  - name: '{socks_name}'\n    type: socks5\n    server: '{s_srv.get('address')}'\n    port: {s_srv.get('port', 1080)}")
                    if s_usr.get('user'): yaml_lines.append(f"    username: '{s_usr.get('user')}'\n    password: '{s_usr.get('pass')}'")
                    has_socks = True
            except: pass

        try:
            v_sett = safe_dict(vless.get('settings'))
            v_srv = safe_dict(safe_list(v_sett.get('vnext'))[0])
            v_usr = safe_dict(safe_list(v_srv.get('users'))[0])
            stream = safe_dict(vless.get('streamSettings'))
            reality = safe_dict(stream.get('realitySettings'))
            
            if not v_srv.get('address'): continue
            yaml_lines.append(f"  - name: '{safe_name}'\n    type: vless\n    server: '{v_srv.get('address')}'\n    port: {v_srv.get('port', 443)}\n    uuid: '{v_usr.get('id')}'\n    network: '{stream.get('network', 'tcp')}'\n    tls: true\n    udp: true")
            if v_usr.get('flow'): yaml_lines.append(f"    flow: '{v_usr.get('flow')}'")
            yaml_lines.append(f"    client-fingerprint: '{reality.get('fingerprint', 'chrome')}'\n    servername: '{reality.get('serverName', 'google.com')}'\n    reality-opts:\n      public-key: '{reality.get('publicKey', '')}'")
            sid = str(reality.get('shortId', ''))
            if sid and all(c in '0123456789abcdefABCDEF' for c in sid): yaml_lines.append(f"      short-id: '{sid}'")
            if has_socks: yaml_lines.append(f"    dialer-proxy: '{socks_name}'")
            valid_nodes += 1
        except: continue
    return "\n".join(yaml_lines) if valid_nodes > 0 else None

class SubHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args): pass
    def do_GET(self):
        url = os.environ.get('SUB_URL')
        yaml_out = None
        try:
            print(f"Fetching subscription from somethingsomething...", flush=True)
            req = urllib.request.Request(url, headers={'User-Agent': 'v2rayNG/1.8.5'})
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read().decode('utf-8', errors='ignore').strip()
                yaml_out = process_something_json(raw)
                if yaml_out:
                    with open(CACHE_FILE, "w") as f: f.write(yaml_out)
                    print("Success! Cache updated.", flush=True)
        except Exception as e:
            print(f"Network error: {e}. Trying to load from cache...", flush=True)

        if not yaml_out and os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, "r") as f: yaml_out = f.read()
            print("Serving from disk cache.", flush=True)

        if yaml_out:
            self.send_response(200)
            self.send_header('Content-type', 'application/yaml')
            self.end_headers()
            self.wfile.write(yaml_out.encode('utf-8'))
        else:
            self.send_response(500)
            self.end_headers()

print("Cleaner with caching started on 8080", flush=True)
HTTPServer(('127.0.0.1', 8080), SubHandler).serve_forever()