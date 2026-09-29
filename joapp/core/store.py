"""SQLite 持久化层。没有 ORM，手写 SQL，够用且零依赖。

任务一张表，完成记录一张表。完成记录按「周期」存（见 models.period_key），
所以每天任务到第二天自动变回没做，不需要任何定时清零。
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path

from ..config import DB_PATH
from .models import REWARD_SCOPES, Reward, Scope, Todo, period_key, reached

SCHEMA = """
CREATE TABLE IF NOT EXISTS todos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    scope       TEXT NOT NULL,
    day         TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS todo_done (
    todo_id  INTEGER NOT NULL REFERENCES todos(id) ON DELETE CASCADE,
    period   TEXT NOT NULL,
    done_at  TEXT NOT NULL,
    PRIMARY KEY (todo_id, period)
);

CREATE TABLE IF NOT EXISTS rewards (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    scope       TEXT NOT NULL,
    percent     INTEGER NOT NULL,
    text        TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

-- 每个奖励每个周期只发一次
CREATE TABLE IF NOT EXISTS reward_claims (
    reward_id   INTEGER NOT NULL REFERENCES rewards(id) ON DELETE CASCADE,
    period      TEXT NOT NULL,
    claimed_at  TEXT NOT NULL,
    PRIMARY KEY (reward_id, period)
);

CREATE TABLE IF NOT EXISTS meta (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL
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
        self._import_legacy_tasks()
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # ---------- 增删改 ----------

    def add(self, title: str, scope: Scope, day: date | None = None) -> Todo:
        todo = Todo(title=title.strip(), scope=scope, day=day or date.today())
        cur = self.conn.execute(
            "INSERT INTO todos (title, scope, day, created_at) VALUES (?,?,?,?)",
            (todo.title, scope.value, todo.day.isoformat(), todo.created_at.isoformat()),
        )
        self.conn.commit()
        todo.id = cur.lastrowid
        return todo

    def delete(self, todo_id: int) -> None:
        self.conn.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
        self.conn.commit()

    def set_done(self, todo: Todo, done: bool, today: date | None = None) -> None:
        period = period_key(todo.scope, today or date.today(), todo.day)
        if done:
            self.conn.execute(
                "INSERT OR IGNORE INTO todo_done (todo_id, period, done_at)"
                " VALUES (?,?,?)",
                (todo.id, period, datetime.now().isoformat()),
            )
        else:
            self.conn.execute(
                "DELETE FROM todo_done WHERE todo_id = ? AND period = ?",
                (todo.id, period),
            )
        self.conn.commit()
        todo.done = done

    # ---------- 读 ----------

    def todos(self, scope: Scope, today: date | None = None) -> list[Todo]:
        """这个分组现在该显示的任务，done 按当前周期算好。

        当天任务：今天加的全显示；以前加的只显示没做完的（拖着的）。
        以后某天的（比如从旧版本导进来的）等到那天再出现。
        """
        today = today or date.today()
        rows = self.conn.execute(
            "SELECT * FROM todos WHERE scope = ? ORDER BY id", (scope.value,)
        ).fetchall()
        out = []
        for r in rows:
            todo = self._todo(r)
            todo.done = self._is_done(todo, today)
            if scope is Scope.TODAY:
                if todo.day > today or (todo.day < today and todo.done):
                    continue
            out.append(todo)
        return out

    def _is_done(self, todo: Todo, today: date) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM todo_done WHERE todo_id = ? AND period = ?",
            (todo.id, period_key(todo.scope, today, todo.day)),
        ).fetchone()
        return row is not None

    def _todo(self, r: sqlite3.Row) -> Todo:
        return Todo(
            id=r["id"],
            title=r["title"],
            scope=Scope(r["scope"]),
            day=_d(r["day"]),
            created_at=_dt(r["created_at"]),
        )

    # ---------- 奖励 ----------

    def add_reward(self, scope: Scope, percent: int, text: str) -> Reward:
        if scope not in REWARD_SCOPES:
            raise ValueError(f"{scope.label}任务不能设奖励")
        reward = Reward(scope=scope, percent=max(1, min(100, int(percent))), text=text.strip())
        cur = self.conn.execute(
            "INSERT INTO rewards (scope, percent, text, created_at) VALUES (?,?,?,?)",
            (scope.value, reward.percent, reward.text, reward.created_at.isoformat()),
        )
        self.conn.commit()
        reward.id = cur.lastrowid
        return reward

    def delete_reward(self, reward_id: int) -> None:
        self.conn.execute("DELETE FROM rewards WHERE id = ?", (reward_id,))
        self.conn.commit()

    def rewards(self, scope: Scope | None = None, today: date | None = None) -> list[Reward]:
        """按分组、百分比排好；earned 表示这个周期已经拿到了。"""
        today = today or date.today()
        sql = "SELECT * FROM rewards"
        args: tuple = ()
        if scope is not None:
            sql += " WHERE scope = ?"
            args = (scope.value,)
        order = {s: i for i, s in enumerate(REWARD_SCOPES)}
        out = []
        for r in self.conn.execute(sql, args).fetchall():
            reward = Reward(
                id=r["id"],
                scope=Scope(r["scope"]),
                percent=r["percent"],
                text=r["text"],
                created_at=_dt(r["created_at"]),
            )
            reward.earned = self._claimed(reward, today)
            out.append(reward)
        out.sort(key=lambda w: (order.get(w.scope, 99), w.percent, w.id))
        return out

    def progress(self, scope: Scope, today: date | None = None) -> tuple[int, int]:
        """(做完几件, 一共几件)，按当前周期算。"""
        todos = self.todos(scope, today)
        return sum(1 for t in todos if t.done), len(todos)

    def claim_reached(self, scope: Scope, today: date | None = None) -> list[Reward]:
        """这个分组刚够线、这个周期还没发过的奖励：记成已发，返回给界面去庆祝。

        发过的就算后来又取消勾选掉回线下，也不会再发第二次。
        """
        today = today or date.today()
        done, total = self.progress(scope, today)
        period = period_key(scope, today)
        fresh = []
        for reward in self.rewards(scope, today):
            if reward.earned or not reached(done, total, reward.percent):
                continue
            self.conn.execute(
                "INSERT OR IGNORE INTO reward_claims (reward_id, period, claimed_at)"
                " VALUES (?,?,?)",
                (reward.id, period, datetime.now().isoformat()),
            )
            reward.earned = True
            fresh.append(reward)
        self.conn.commit()
        return fresh

    def _claimed(self, reward: Reward, today: date) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM reward_claims WHERE reward_id = ? AND period = ?",
            (reward.id, period_key(reward.scope, today)),
        ).fetchone()
        return row is not None

    # ---------- 旧版本数据 ----------

    def _import_legacy_tasks(self) -> None:
        """旧版本（按天排计划那一版）的 tasks 表：没做完的搬成当天任务，只搬一次。

        旧表原样留着不动 —— 想翻旧记录的话还在库里。
        """
        if self.conn.execute(
            "SELECT 1 FROM meta WHERE key = 'legacy_imported'"
        ).fetchone():
            return
        has_legacy = self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'tasks'"
        ).fetchone()
        if has_legacy:
            columns = {r["name"] for r in self.conn.execute("PRAGMA table_info(tasks)")}
            if {"title", "day", "status", "created_at"} <= columns:
                self.conn.execute(
                    "INSERT INTO todos (title, scope, day, created_at)"
                    " SELECT title, 'today', day, created_at FROM tasks"
                    " WHERE status IN ('todo', 'doing') ORDER BY id"
                )
        self.conn.execute(
            "INSERT INTO meta (key, value) VALUES ('legacy_imported', ?)",
            (datetime.now().isoformat(),),
        )
