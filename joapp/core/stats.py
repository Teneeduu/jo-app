"""活动记录图用到的纯计算：格子怎么排、颜色几档、连续了几天。不碰数据库，不碰 Qt。"""

from __future__ import annotations

from datetime import date, timedelta

LEVELS = 4  # 有记录的日子分 4 档颜色，加上「没有」一共 5 档，跟 GitHub 一样


def weeks(start: date, end: date) -> list[list[date | None]]:
    """按周切成列，每列 7 格，周一在最上面。范围外的格子是 None（不画）。"""
    first = start - timedelta(days=start.weekday())  # 往前退到周一
    columns = []
    day = first
    while day <= end:
        column = []
        for _ in range(7):
            column.append(day if start <= day <= end else None)
            day += timedelta(days=1)
        columns.append(column)
    return columns


def level(count: int, busiest: int) -> int:
    """0 = 没有；1~4 按当前范围里最忙那天的比例分档（最忙那天总是最深）。"""
    if count <= 0 or busiest <= 0:
        return 0
    return max(1, min(LEVELS, -(-count * LEVELS // busiest)))


def streaks(days: set[date], today: date) -> tuple[int, int]:
    """(当前连续天数, 历史最长连续天数)。

    今天还没做事不算断 —— 当前连续从今天往回数；今天是空的就从昨天往回数。
    """
    if not days:
        return 0, 0
    longest = run = 0
    prev = None
    for d in sorted(days):
        run = run + 1 if prev is not None and d - prev == timedelta(days=1) else 1
        longest = max(longest, run)
        prev = d

    cursor = today if today in days else today - timedelta(days=1)
    current = 0
    while cursor in days:
        current += 1
        cursor -= timedelta(days=1)
    return current, longest


def last_year(today: date) -> tuple[date, date]:
    """「过去一年」：今天所在这周往前一共 53 列，跟 GitHub 一样。"""
    this_monday = today - timedelta(days=today.weekday())
    return this_monday - timedelta(weeks=52), today


def year_range(year: int, today: date) -> tuple[date, date]:
    """某一年：1 月 1 日到 12 月 31 日；今年只到今天。"""
    end = date(year, 12, 31)
    return date(year, 1, 1), min(end, today)
