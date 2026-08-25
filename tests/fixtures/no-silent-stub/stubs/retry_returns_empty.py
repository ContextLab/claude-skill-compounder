"""Taxonomy 7: a retry loop whose exhaustion path returns empty."""

import urllib.error
import urllib.request


def fetch_incidents(url, attempts=3):
    for _ in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=1) as resp:
                return resp.read().decode("utf-8").splitlines()
        except (urllib.error.URLError, OSError) as exc:
            last = exc
    return []


def main():
    incidents = fetch_incidents("http://127.0.0.1:1/incidents")
    print(f"open incidents: {len(incidents)}")


if __name__ == "__main__":
    main()
