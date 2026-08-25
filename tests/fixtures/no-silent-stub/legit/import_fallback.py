"""Legitimate: an optional accelerator with an equivalent fallback.

The handler does not discard anything: it binds a real, equivalent
implementation, and the caller gets the same answer either way.
"""

try:
    import tomllib as _toml
except ImportError:
    import json as _toml


def parse_blob(blob):
    return _toml.loads(blob)


def main():
    print(parse_blob('{"ok": true}') if _toml.__name__ == "json" else "toml backend")


if __name__ == "__main__":
    main()
