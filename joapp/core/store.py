"""SQLite 持久化层。没有 ORM，手写 SQL，够用且零依赖。"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path

from ..config import DB_PATH
from .models import Goal, Task, TaskStatus, WorkSession

SCHEMA = """
CREATE TABLE IF NOT EXISTS goals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    deadline    TEXT,
    target      REAL NOT NULL DEFAULT 100,
    progress    REAL NOT NULL DEFAULT 0,
    unit        TEXT NOT NULL DEFAULT '%',
    archived    INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    title             TEXT NOT NULL,
    day               TEXT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'todo',
    estimate_minutes  INTEGER NOT NULL DEFAULT 30,
    spent_minutes     INTEGER NOT NULL DEFAULT 0,
    goal_id           INTEGER REFERENCES goals(id) ON DELETE SET NULL,
    note              TEXT NOT NULL DEFAULT '',
    created_at        TEXT NOT NULL,
    done_at           TEXT
);
CREATE INDEX IF NOT EXISTS idx_tasks_day ON tasks(day);

CREATE TABLE IF NOT EXISTS sessions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id      INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
    started_at   TEXT NOT NULL,
    ended_at     TEXT,
    kind         TEXT NOT NULL DEFAULT 'focus',
    interrupted  INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_sessions_started ON sessions(started_at);

CREATE TABLE IF NOT EXISTS nudge_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kind        TEXT NOT NULL,
    title       TEXT NOT NULL,
    body        TEXT NOT NULL DEFAULT '',
    source      TEXT NOT NULL DEFAULT 'rules',
    created_at  TEXT NOT NULL
);
"""


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _d(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


class Store:
    def __init__(self, path: Path | str = DB_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # ---------- tasks ----------

    def add_task(self, task: Task) -> Task:
        cur = self.conn.execute(
            "INSERT INTO tasks (title, day, status, estimate_minutes, spent_minutes,"
            " goal_id, note, created_at, done_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                task.title,
                task.day.isoformat(),
                task.status.value,
                task.estimate_minutes,
                task.spent_minutes,
                task.goal_id,
                task.note,
                task.created_at.isoformat(),
                task.done_at.isoformat() if task.done_at else None,
            ),
        )
        self.conn.commit()
        task.id = cur.lastrowid
        return task

    def tasks_for(
        self, day: date | None = None, include_dropped: bool = False
    ) -> list[Task]:
        """默认不含已丢弃的 —— 顺延到明天之后，它们不该再出现在今天的清单里，
        更不该被算进「完成 x/y」的分母。"""
        day = day or date.today()
        sql = "SELECT * FROM tasks WHERE day = ?"
        if not include_dropped:
            sql += " AND status != 'dropped'"
        sql += " ORDER BY id"
        rows = self.conn.execute(sql, (day.isoformat(),)).fetchall()
        return [self._task(r) for r in rows]

    def open_tasks(self, day: date | None = None) -> list[Task]:
        return [t for t in self.tasks_for(day) if t.is_open]

    def set_task_status(self, task_id: int, status: TaskStatus) -> None:
        done_at = datetime.now().isoformat() if status is TaskStatus.DONE else None
        self.conn.execute(
            "UPDATE tasks SET status = ?, done_at = ? WHERE id = ?",
            (status.value, done_at, task_id),
        )
        self.conn.commit()

    def add_spent(self, task_id: int, minutes: float) -> None:
        self.conn.execute(
            "UPDATE tasks SET spent_minutes = spent_minutes + ? WHERE id = ?",
            (round(minutes), task_id),
        )
        self.conn.commit()

    def _task(self, r: sqlite3.Row) -> Task:
        return Task(
            id=r["id"],
            title=r["title"],
            day=_d(r["day"]),
            status=TaskStatus(r["status"]),
            estimate_minutes=r["estimate_minutes"],
            spent_minutes=r["spent_minutes"],
            goal_id=r["goal_id"],
            note=r["note"],
            created_at=_dt(r["created_at"]),
            done_at=_dt(r["done_at"]),
        )

    # ---------- goals ----------

    def add_goal(self, goal: Goal) -> Goal:
        cur = self.conn.execute(
            "INSERT INTO goals (title, deadline, target, progress, unit, archived,"
            " created_at) VALUES (?,?,?,?,?,?,?)",
            (
                goal.title,
                goal.deadline.isoformat() if goal.deadline else None,
                goal.target,
                goal.progress,
                goal.unit,
                int(goal.archived),
                goal.created_at.isoformat(),
            ),
        )
        self.conn.commit()
        goal.id = cur.lastrowid
        return goal

    def goals(self, include_archived: bool = False) -> list[Goal]:
        sql = "SELECT * FROM goals"
        if not include_archived:
            sql += " WHERE archived = 0"
        sql += " ORDER BY COALESCE(deadline, '9999-12-31'), id"
        return [self._goal(r) for r in self.conn.execute(sql).fetchall()]

    def bump_goal(self, goal_id: int, delta: float) -> None:
        self.conn.execute(
            "UPDATE goals SET progress = MAX(0, progress + ?) WHERE id = ?",
            (delta, goal_id),
        )
        self.conn.commit()

    def _goal(self, r: sqlite3.Row) -> Goal:
        return Goal(
            id=r["id"],
            title=r["title"],
            deadline=_d(r["deadline"]),
            target=r["target"],
            progress=r["progress"],
            unit=r["unit"],
            archived=bool(r["archived"]),
            created_at=_dt(r["created_at"]),
        )

    # ---------- sessions ----------

    def start_session(self, task_id: int | None, kind: str = "focus") -> WorkSession:
        s = WorkSession(task_id=task_id, kind=kind)
        cur = self.conn.execute(
            "INSERT INTO sessions (task_id, started_at, kind, interrupted)"
            " VALUES (?,?,?,0)",
            (task_id, s.started_at.isoformat(), kind),
        )
        self.conn.commit()
        s.id = cur.lastrowid
        return s

    def end_session(self, session: WorkSession, interrupted: bool = False) -> None:
        session.ended_at = datetime.now()
        session.interrupted = interrupted
        self.conn.execute(
            "UPDATE sessions SET ended_at = ?, interrupted = ? WHERE id = ?",
            (session.ended_at.isoformat(), int(interrupted), session.id),
        )
        if session.task_id and session.kind == "focus":
            self.add_spent(session.task_id, session.minutes)
        self.conn.commit()

    def focus_minutes_today(self) -> float:
        rows = self.conn.execute(
            "SELECT started_at, ended_at FROM sessions"
            " WHERE kind = 'focus' AND started_at >= ?",
            (datetime.combine(date.today(), datetime.min.time()).isoformat(),),
        ).fetchall()
        total = 0.0
        for r in rows:
            end = _dt(r["ended_at"]) or datetime.now()
            total += (end - _dt(r["started_at"])).total_seconds() / 60.0
        return total

    # ---------- nudges ----------

    def log_nudge(self, kind: str, title: str, body: str, source: str) -> None:
        self.conn.execute(
            "INSERT INTO nudge_log (kind, title, body, source, created_at)"
            " VALUES (?,?,?,?,?)",
            (kind, title, body, source, datetime.now().isoformat()),
        )
        self.conn.commit()

    def last_nudge_at(self, kind: str) -> datetime | None:
        row = self.conn.execute(
            "SELECT created_at FROM nudge_log WHERE kind = ?"
            " ORDER BY id DESC LIMIT 1",
            (kind,),
        ).fetchone()
        return _dt(row["created_at"]) if row else None

    def planned_today(self) -> bool:
        """今天是否已经录过任务（用来决定开机要不要弹晨间窗口）。

        丢弃的不算 —— 把今天的事全顺延走之后，等于还没规划，该重新问一遍。
        """
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM tasks WHERE day = ? AND status != 'dropped'",
            (date.today().isoformat(),),
        ).fetchone()
        return row["n"] > 0
