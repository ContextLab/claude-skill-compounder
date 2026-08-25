"""Taxonomy 2: a handler that discards the error and continues."""

import json


def load_settings(path):
    settings = {"theme": "dark"}
    try:
        with open(path, encoding="utf-8") as fh:
            settings.update(json.load(fh))
    except:
        pass
    return settings


def parse_port(raw):
    try:
        return int(raw)
    except ValueError:
        return 8080


def main():
    print(load_settings("/nonexistent/settings.json"))
    print(parse_port("not-a-port"))


if __name__ == "__main__":
    main()
