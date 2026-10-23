"""Streak and heatmap rules (services/habit_stats.py) on fixed dates.

2026-10-05 is a Monday. D(n) = 2026-10-(05+n), so D(0)=Mon … D(6)=Sun.
"""

from datetime import date, timedelta

from ontherecord.models import CheckStatus
from ontherecord.services.habit_stats import Schedule, compute_heatmap, compute_stats

DONE, SKIP = CheckStatus.DONE, CheckStatus.SKIPPED
MON = date(2026, 10, 5)
DAILY = [1, 2, 3, 4, 5, 6, 7]
MWF = [1, 3, 5]


def d(n: int) -> date:
    return MON + timedelta(days=n)


def test_consecutive_done_days_build_a_streak() -> None:
    stats = compute_stats(Schedule(DAILY, d(0)), {d(0): DONE, d(1): DONE, d(2): DONE}, today=d(2))
    assert (stats.current_streak, stats.longest_streak) == (3, 3)
    assert stats.completion_rate == 1.0


def test_a_missed_day_resets_the_current_streak() -> None:
    checks = {d(0): DONE, d(1): DONE, d(3): DONE}  # d(2) missed
    stats = compute_stats(Schedule(DAILY, d(0)), checks, today=d(3))
    assert (stats.current_streak, stats.longest_streak, stats.missed_count) == (1, 2, 1)
    assert stats.completion_rate == 3 / 4


def test_today_is_pending_not_missed() -> None:
    stats = compute_stats(Schedule(DAILY, d(0)), {d(0): DONE, d(1): DONE}, today=d(2))
    assert stats.current_streak == 2
    assert stats.missed_count == 0
    assert stats.expected_count == 2


def test_skipped_neither_counts_nor_breaks() -> None:
    checks = {d(0): DONE, d(1): SKIP, d(2): DONE}
    stats = compute_stats(Schedule(DAILY, d(0)), checks, today=d(2))
    assert stats.current_streak == 2
    assert (stats.skipped_count, stats.expected_count) == (1, 2)
    assert stats.completion_rate == 1.0


def test_unscheduled_days_are_ignored() -> None:
    # Mon/Wed/Fri habit: Tue and Thu with no check are not misses.
    checks = {d(0): DONE, d(2): DONE, d(4): DONE}
    stats = compute_stats(Schedule(MWF, d(0)), checks, today=d(4))
    assert (stats.current_streak, stats.missed_count, stats.completion_rate) == (3, 0, 1.0)


def test_done_on_an_unscheduled_day_is_a_bonus() -> None:
    checks = {d(0): DONE, d(1): DONE}  # Tue isn't scheduled
    stats = compute_stats(Schedule(MWF, d(0)), checks, today=d(1))
    assert (stats.current_streak, stats.done_count) == (2, 2)
    assert stats.expected_count == 1  # the rate only counts scheduled days
    assert stats.completion_rate == 1.0


def test_days_before_started_on_are_ignored() -> None:
    stats = compute_stats(Schedule(DAILY, d(3)), {d(1): DONE, d(3): DONE}, today=d(3))
    assert (stats.done_count, stats.missed_count) == (1, 0)


def test_nothing_decided_yet_has_no_rate() -> None:
    stats = compute_stats(Schedule(DAILY, d(0)), {}, today=d(0))
    assert stats.completion_rate is None
    assert stats.current_streak == 0


def test_archived_habit_stops_expecting_days() -> None:
    # Archived on d(3): last expected day is d(2). Later days aren't misses.
    stats = compute_stats(
        Schedule(DAILY, d(0), ends_on=d(2)), {d(0): DONE, d(1): DONE, d(2): DONE}, today=d(6)
    )
    assert (stats.current_streak, stats.missed_count) == (3, 0)


def test_heatmap_counts_per_day() -> None:
    daily = Schedule(DAILY, d(0))
    mwf = Schedule(MWF, d(0))
    days = compute_heatmap(
        [daily, mwf],
        [{d(0): DONE, d(1): SKIP}, {d(0): DONE, d(1): DONE}],
        start=d(0),
        end=d(2),
    )
    assert [(x.date, x.scheduled, x.done, x.skipped) for x in days] == [
        (d(0), 2, 2, 0),  # Mon: both expected, both done
        (d(1), 1, 1, 1),  # Tue: only daily expected; it was skipped; MWF bonus done
        (d(2), 2, 0, 0),  # Wed: both expected, nothing done
    ]


def test_heatmap_ignores_days_outside_a_habits_range() -> None:
    days = compute_heatmap([Schedule(DAILY, d(1))], [{d(0): DONE}], start=d(0), end=d(1))
    assert [(x.scheduled, x.done) for x in days] == [(0, 0), (1, 0)]
