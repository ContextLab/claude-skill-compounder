"""Legitimate: a documented default parameter.

The default is visible in the signature, so a caller who passes nothing has
chosen it. Nothing here pretends to be a value it did not compute.
"""

DEFAULT_TIMEOUT_S = 30.0


def request_budget(payload_bytes, timeout_s=DEFAULT_TIMEOUT_S):
    """Seconds to allow for `payload_bytes`, never less than `timeout_s`."""
    return max(timeout_s, payload_bytes / 1_000_000.0)


def main():
    print(request_budget(2_000_000))
    print(request_budget(2_000_000, timeout_s=5.0))


if __name__ == "__main__":
    main()
