"""Legitimate: a retry loop whose exhaustion path raises."""

import urllib.error
import urllib.request


def fetch_incidents(url, attempts=3):
    last_error = None
    for _ in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=1) as resp:
                return resp.read().decode("utf-8").splitlines()
        except (urllib.error.URLError, OSError) as exc:
            last_error = exc
    raise ConnectionError(
        f"fetch_incidents: {attempts} attempts to {url} all failed"
    ) from last_error


def main():
    try:
        fetch_incidents("http://127.0.0.1:1/incidents")
    except ConnectionError as exc:
        print(f"refused: {exc}")


if __name__ == "__main__":
    main()
