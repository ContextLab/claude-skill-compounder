"""Legitimate: handlers that translate or annotate, then re-raise."""

import logging

log = logging.getLogger(__name__)


class ConfigError(Exception):
    pass


def read_port(raw):
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"read_port: {raw!r} is not an integer port") from exc


def read_file(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        log.warning("read_file: %s could not be opened", path)
        raise


def main():
    try:
        read_port("eighty")
    except ConfigError as exc:
        print(f"refused: {exc}")


if __name__ == "__main__":
    main()
