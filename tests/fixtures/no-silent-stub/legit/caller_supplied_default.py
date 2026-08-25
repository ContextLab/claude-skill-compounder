"""Legitimate: the miss path returns the default the caller passed in."""

_SETTINGS = {"retries": 3}


def get_setting(key, default):
    """The stored value for `key`, or the caller's own `default`."""
    if key not in _SETTINGS:
        return default
    return _SETTINGS[key]


def main():
    print(get_setting("retries", 1))
    print(get_setting("colour", "unset"))


if __name__ == "__main__":
    main()
