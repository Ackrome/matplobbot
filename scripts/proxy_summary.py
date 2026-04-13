import json
import os
import sys
import urllib.request


DEFAULT_URL = os.environ.get("PROXY_SUMMARY_URL", "http://127.0.0.1:8080/summary")


def fetch_summary(url):
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def print_group(name, payload):
    print(f"{name}:")
    print(f"  selected: {payload.get('selected')}")
    print(f"  candidates: {payload.get('candidate_count')}")
    top_candidates = payload.get("top_candidates") or []
    if not top_candidates:
        print("  top: none")
        return

    for item in top_candidates:
        delay = item.get("delay")
        alive = item.get("alive")
        rendered_delay = "n/a" if delay is None else f"{delay} ms"
        print(f"  - {item.get('name')} | delay={rendered_delay} | alive={alive}")


def main():
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    payload = fetch_summary(url)
    state = payload.get("state") or {}
    last_build = state.get("last_build") or {}

    print("Proxy summary")
    print(f"  merged entries: {last_build.get('merged_entries')}")
    print(f"  outline entries: {last_build.get('outline_entries')}")
    print(f"  subscription entries: {last_build.get('subscription_entries')}")
    print_group("Telegram", payload.get("telegram") or {})
    print_group("OpenAI", payload.get("openai") or {})


if __name__ == "__main__":
    main()
