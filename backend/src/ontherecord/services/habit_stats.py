"""Streaks, completion and heatmap maths. Pure functions over dates, no database,
so every rule is unit-testable with fixed dates.

Rules (ARCHITECTURE › D8):
- A day is *expected* if it's on or after `started_on`, on or before `ends_on`
  (the day before archiving), and its ISO weekday is in `schedule_days`.
- `done` counts and extends the streak, even on an unscheduled day (a bonus).
- `skipped` neither counts nor breaks the streak.
- An expected day with no check is a miss and resets the streak, except today,
  which is still pending until it's over.
"""

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from ontherecord.models import CheckStatus


@dataclass(frozen=True)
class Schedule:
    schedule_days: Sequence[int]
    started_on: date
    ends_on: date | None = None  # last expected day; None = still active

    def expects(self, day: date) -> bool:
        return self.in_range(day) and day.isoweekday() in self.schedule_days

    def in_range(self, day: date) -> bool:
        return self.started_on <= day and (self.ends_on is None or day <= self.ends_on)


@dataclass(frozen=True)
class Stats:
    current_streak: int
    longest_streak: int
    done_count: int  # all done days, including unscheduled bonuses
    skipped_count: int
    missed_count: int
    expected_count: int  # expected days that are decided: done or missed (not skipped/pending)
    completion_rate: float | None  # done-on-expected-days / expected_count


def days(start: date, end: date) -> Iterator[date]:
    """Every date from start to end, inclusive."""
    for offset in range((end - start).days + 1):
        yield start + timedelta(days=offset)


def compute_stats(schedule: Schedule, checks: Mapping[date, CheckStatus], today: date) -> Stats:
    last = today if schedule.ends_on is None else min(today, schedule.ends_on)
    streak = longest = done = skipped = missed = done_expected = 0

    for day in days(schedule.started_on, last):
        status = checks.get(day)
        expected = schedule.expects(day)
        if status is CheckStatus.DONE:
            done += 1
            done_expected += expected
            streak += 1
            longest = max(longest, streak)
        elif status is CheckStatus.SKIPPED:
            skipped += expected
        elif expected and day != today:
            missed += 1
            streak = 0

    decided = done_expected + missed
    return Stats(
        current_streak=streak,
        longest_streak=longest,
        done_count=done,
        skipped_count=skipped,
        missed_count=missed,
        expected_count=decided,
        completion_rate=done_expected / decided if decided else None,
    )


@dataclass(frozen=True)
class HeatmapDay:
    date: date
    scheduled: int  # habits expected that day
    done: int  # done checks that day (can exceed `scheduled` with bonus days)
    skipped: int


def compute_heatmap(
    schedules: Sequence[Schedule],
    checks: Sequence[Mapping[date, CheckStatus]],
    start: date,
    end: date,
) -> list[HeatmapDay]:
    """One entry per day. `checks[i]` belongs to `schedules[i]`. Clients derive the
    colour level from done/scheduled (design system `heat-0`…`heat-4`, `heat-skip`)."""
    result = []
    for day in days(start, end):
        scheduled = done = skipped = 0
        for schedule, habit_checks in zip(schedules, checks, strict=True):
            scheduled += schedule.expects(day)
            if not schedule.in_range(day):
                continue
            status = habit_checks.get(day)
            done += status is CheckStatus.DONE
            skipped += status is CheckStatus.SKIPPED
        result.append(HeatmapDay(day, scheduled, done, skipped))
    return result
