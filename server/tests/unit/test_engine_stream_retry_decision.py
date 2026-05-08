"""
Unit tests for the synchronous part of the stream-retry decision matrix
(see stream-level retry spec §4.4). The full engine — DB, tool loop, SSE plumbing — is
out of scope here; we exercise the pure decision function so future tweaks to
the matrix are caught immediately, without spinning up a database.
"""
from __future__ import annotations

import pytest

from app.services.agent_engine_service import (
    StreamRetryAction,
    decide_stream_retry_action,
)


# Defaults pulled from settings.py so the table below stays human-readable.
RETRY_MAX = 2
RESET_MAX = 50


def _decide(
    *,
    partial_content_chars: int,
    retry_count: int,
    retry_enabled: bool = True,
    retry_max: int = RETRY_MAX,
    reset_max_chars: int = RESET_MAX,
) -> StreamRetryAction:
    return decide_stream_retry_action(
        partial_content_chars=partial_content_chars,
        retry_count=retry_count,
        retry_enabled=retry_enabled,
        retry_max=retry_max,
        reset_max_chars=reset_max_chars,
    )


# ── Healthy retry paths ──


def test_no_chars_yet_under_budget_does_silent_retry():
    assert _decide(partial_content_chars=0, retry_count=0) is StreamRetryAction.SILENT_RETRY


def test_no_chars_yet_after_one_failure_still_silent():
    assert _decide(partial_content_chars=0, retry_count=1) is StreamRetryAction.SILENT_RETRY


def test_some_chars_within_reset_threshold_does_reset_retry():
    assert _decide(partial_content_chars=10, retry_count=0) is StreamRetryAction.RESET_RETRY


def test_chars_at_reset_threshold_still_resets():
    """Boundary: equal to RESET_MAX is allowed (the design uses ≤)."""
    assert _decide(partial_content_chars=RESET_MAX, retry_count=0) is StreamRetryAction.RESET_RETRY


# ── Give-up paths ──


def test_master_switch_off_gives_up_immediately():
    assert _decide(partial_content_chars=0, retry_count=0, retry_enabled=False) is StreamRetryAction.GIVE_UP


def test_retry_budget_exhausted_gives_up():
    assert _decide(partial_content_chars=0, retry_count=RETRY_MAX) is StreamRetryAction.GIVE_UP


def test_chars_over_reset_threshold_gives_up_even_under_budget():
    """Avoid duplicate output once we're past the threshold, stream-level retry spec §4.4 row 4."""
    assert _decide(partial_content_chars=RESET_MAX + 1, retry_count=0) is StreamRetryAction.GIVE_UP


def test_exhausted_takes_priority_over_chars_window():
    """Both conditions present — either of them alone gives up; their AND must too."""
    assert _decide(partial_content_chars=10, retry_count=RETRY_MAX) is StreamRetryAction.GIVE_UP


def test_zero_retry_max_means_never_retry():
    """Edge case: ops sets max=0 to fully disable retries while keeping detection."""
    assert _decide(partial_content_chars=0, retry_count=0, retry_max=0) is StreamRetryAction.GIVE_UP


def test_zero_reset_max_forces_silent_retry_for_pure_zero():
    """If ops sets RESET_MAX=0 (only allow silent retries), partial>0 ⇒ give up."""
    assert _decide(partial_content_chars=0, retry_count=0, reset_max_chars=0) is StreamRetryAction.SILENT_RETRY
    assert _decide(partial_content_chars=1, retry_count=0, reset_max_chars=0) is StreamRetryAction.GIVE_UP


# ── Documented design table replication ──


@pytest.mark.parametrize(
    "partial,retry,enabled,expected",
    [
        # (partial_chars, retry_count, retry_enabled, expected_action)
        (0, 0, True, StreamRetryAction.SILENT_RETRY),
        (1, 0, True, StreamRetryAction.RESET_RETRY),
        (50, 0, True, StreamRetryAction.RESET_RETRY),
        (51, 0, True, StreamRetryAction.GIVE_UP),
        (10, 2, True, StreamRetryAction.GIVE_UP),  # exhausted
        (0, 0, False, StreamRetryAction.GIVE_UP),  # disabled
    ],
)
def test_design_matrix_table(partial, retry, enabled, expected):
    assert _decide(
        partial_content_chars=partial,
        retry_count=retry,
        retry_enabled=enabled,
    ) is expected
