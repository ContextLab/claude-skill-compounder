"""The same package in a flat layout, where the working directory shadows sys.path.

This is the layout the import check must report as SPLIT once a non-editable copy
is installed: the repo root loads ./mypkg while everything else loads site-packages.
"""
from setuptools import setup

setup(name="mypkg", version="0.1.0", packages=["mypkg"])
