"""Shared types + helpers for check implementations."""
from __future__ import annotations

from typing import Callable, Optional, Tuple

# A check function takes no arguments and returns (status, error).
#   status is "ok" or "fail"
#   error is None when ok, a short reason string when fail
# Any exception raised will be caught upstream and recorded as ("fail", repr).
CheckFn = Callable[[], Tuple[str, Optional[str]]]
