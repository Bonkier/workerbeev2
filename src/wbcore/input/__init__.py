# SPDX-License-Identifier: GPL-3.0-or-later
"""Input: FHD-aware mouse driving on top of an InputBackend.

Public surface is intentionally small: `Mouse` is the only class
callers need. The backend protocol is exported for adapters/tests.
"""
from .mouse import Mouse, Point
from .types import InputBackend

__all__ = ["Mouse", "Point", "InputBackend"]
