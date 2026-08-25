"""Minimal installable package (src layout) for tests/test_seed_stale.py.

setup.py rather than pyproject.toml on purpose: it installs offline with
`--no-index --no-build-isolation` against the setuptools that `python -m venv`
already provides, so no fixture here needs the network.
"""
from setuptools import setup

setup(name="mypkg", version="0.1.0", packages=["mypkg"], package_dir={"": "src"})
