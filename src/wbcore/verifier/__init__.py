# SPDX-License-Identifier: GPL-3.0-or-later
"""Verifier: poll-until-found + click composition.

Replaces the retry loop inside legacy `Locate.check`. Sleep is
injected so tests run at zero wall time.
"""
from .verifier import SleepFn, Verifier, VerifyTarget

__all__ = ["Verifier", "SleepFn", "VerifyTarget"]
