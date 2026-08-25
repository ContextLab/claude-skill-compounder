"""Taxonomy 8: a cache miss silently served a default."""

DEFAULT_PREFS = {"theme": "light", "digest": "weekly", "locale": "en-US"}
_CACHE = {"u-1": {"theme": "dark", "digest": "never", "locale": "de-DE"}}


def load_preferences(user_id):
    hit = _CACHE.get(user_id)
    if hit is None:
        return DEFAULT_PREFS
    return hit


def main():
    print(load_preferences("u-1"))
    print(load_preferences("u-999"))


if __name__ == "__main__":
    main()
