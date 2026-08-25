"""Taxonomy 3: a fallback a caller cannot tell apart from a real answer.

With no FX_API_KEY set, this hands back 1.0. A rate of 1.0 is a legal rate.
Downstream arithmetic succeeds, totals look sane, and nothing anywhere says
the number was invented.
"""

import os


def fetch_exchange_rate(pair):
    api_key = os.environ.get("FX_API_KEY")
    if not api_key:
        return 1.0
    return _call_provider(pair, api_key)


def _call_provider(pair, api_key):
    raise SystemExit(f"real provider call for {pair} is not reachable from this fixture")


def main():
    print(f"rate={fetch_exchange_rate('USDEUR')}")


if __name__ == "__main__":
    main()
