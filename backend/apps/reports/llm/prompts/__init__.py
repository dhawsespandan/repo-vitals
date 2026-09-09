"""Prompt text, kept out of the code that calls the model.

A prompt is the specification of what a generation may say, so it is versioned,
reviewable and diffable on its own rather than inlined at a call site. Phase 8
adds `per_dependency.py` beside `combined.py`; both are read by
`apps.reports.llm.groq_client`, which knows nothing about what it is sending.
"""

from .combined import COMBINED_SYSTEM_PROMPT, build_combined_user_prompt

__all__ = ["COMBINED_SYSTEM_PROMPT", "build_combined_user_prompt"]
