"""Minimal installable package used by tests/test_seed_stale.py.

Deliberately setup.py rather than pyproject.toml: it installs offline with
`--no-index --no-build-isolation` against the setuptools that `python -m venv`
already provides, so the fixture needs no network.
"""
from setuptools import setup

setup(name="widget", version="0.1.0", packages=["widget"], package_dir={"": "src"})
