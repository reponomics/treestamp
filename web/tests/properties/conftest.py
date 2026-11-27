"""Hypothesis profiles for this property suite."""

import os

from hypothesis import settings

# derandomize=False overrides the fixed-seed profile Hypothesis loads under CI.
_HYPOTHESIS_DEFAULT = settings.get_profile("default")
settings.register_profile(
    "ordinary",
    _HYPOTHESIS_DEFAULT,
    max_examples=100,
    deadline=None,
    derandomize=False,
    print_blob=True,
)
settings.register_profile(
    "extended",
    _HYPOTHESIS_DEFAULT,
    max_examples=1000,
    deadline=None,
    derandomize=False,
    print_blob=True,
)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "ordinary"))
