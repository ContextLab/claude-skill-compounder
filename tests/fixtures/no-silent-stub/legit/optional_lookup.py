"""Legitimate: a typed optional return the caller is forced to check."""

from typing import Optional

_ROWS = {"u-1": {"name": "Ada"}}


def find_user(user_id: str) -> Optional[dict]:
    """The stored row for `user_id`, or None when there is no such row."""
    return _ROWS.get(user_id)


def greet(user_id: str) -> str:
    row = find_user(user_id)
    if row is None:
        raise KeyError(f"greet: no user row for {user_id!r}")
    return f"hello {row['name']}"


def main():
    print(greet("u-1"))


if __name__ == "__main__":
    main()
