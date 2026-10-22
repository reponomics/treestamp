"""
Online editor for creating and maintaining directory trees for project documentation,
providing a hosted interface for the treestamp package.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("treestamp-web")
except PackageNotFoundError:
    __version__ = "unknown"
