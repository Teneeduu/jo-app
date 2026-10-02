"""SQLite 持久化层。没有 ORM，手写 SQL，够用且零依赖。

任务一张表，完成记录一张表。完成记录按「周期」存（见 models.period_key），
换周期时什么都不用删，读的时候换个 key 就自然变回没做。

每天任务的周期不看日历，是「轮」：meta 表里记着当前这一轮的 key，
按「重新开始」（reset）就换一个新 key —— 每天任务全变回没做，
每天的奖励也能重新拿。旧一轮的记录原样留着。

每周 / 每年照常按日历换周期，也能手动「重新开始」：在日历周期后面加一段
`#n`（`2026-W40#2`）。到了下周 / 明年日历周期变了，后缀自然不再生效。

任务的显示顺序存在 todos.position，同一分组内调（move）。

活动记录（activity）单独一张表，只追加：勾掉一件事、拿到一个奖励各记一条，
标题当场抄一份。删任务、删奖励都不动它 —— 历史是历史。
取消勾选是例外：那说明刚才是点错了，对应的那条一起撤掉。
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

from ..config import DB_PATH
from .models import REWARD_SCOPES, Activity, Reward, Scope, Todo, period_key, reached

SCHEMA = """
CREATE TABLE IF NOT EXISTS todos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    scope       TEXT NOT NULL,
    day         TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    position    INTEGER NOT NULL DEFAULT 0
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

-- 活动记录：只追加。ref_id 指向任务 / 奖励，但不设外键 —— 删了也留着
CREATE TABLE IF NOT EXISTS activity (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    kind    TEXT NOT NULL,
    ref_id  INTEGER,
    period  TEXT,
    title   TEXT NOT NULL,
    scope   TEXT,
    at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_activity_at ON activity(at);

CREATE TABLE IF NOT EXISTS meta (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL
);
"""


# 除了每天（只有手动），每周 / 每年也能手动重来
MANUAL_ROUND_SCOPES = (Scope.WEEKLY, Scope.YEARLY)


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
        self._add_position_column()
        self._import_legacy_tasks()
        self._backfill_activity()
        self._daily_round = self._load_daily_round()
        self._manual_rounds = {s: self._load_manual_round(s) for s in MANUAL_ROUND_SCOPES}
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # ---------- 每天任务的「轮」 ----------

    def _load_daily_round(self) -> str:
        row = self.conn.execute("SELECT value FROM meta WHERE key = 'daily_round'").fetchone()
        if row:
            return row["value"]
        # 第一次（包括从按日期清零的旧版本升上来）：第一轮就是「今天」，
        # 这样今天已经勾掉的每天任务、已经拿到的每天奖励都还算数。
        first = date.today().isoformat()
        self._set_meta("daily_round", first)
        self._set_meta("daily_round_started", datetime.now().isoformat())
        return first

    def _load_manual_round(self, scope: Scope) -> tuple[str, int, datetime | None]:
        """每周 / 每年上一次手动重来：(当时的日历周期, 第几次, 什么时候)。"""
        row = self.conn.execute(
            "SELECT value FROM meta WHERE key = ?", (f"round_{scope.value}",)
        ).fetchone()
        if not row:
            return "", 0, None
        base, _, n = row["value"].rpartition("|")
        started = self.conn.execute(
            "SELECT value FROM meta WHERE key = ?", (f"round_{scope.value}_started",)
        ).fetchone()
        return base, int(n), _dt(started["value"]) if started else None

    def reset(self, scope: Scope, today: date | None = None) -> None:
        """重新开始一轮：这个分组的任务全部变回没做，这个分组的奖励可以重新拿。"""
        now = datetime.now()
        if scope is Scope.DAILY:
            # key 用递增编号，不用时间戳 —— Windows 时钟精度有限，连按两下可能拿到同一个时间，
            # 第二下就等于没按。时间另存一份只给界面显示。
            row = self.conn.execute(
                "SELECT value FROM meta WHERE key = 'daily_round_count'"
            ).fetchone()
            count = int(row["value"]) + 1 if row else 1
            self._daily_round = f"round-{count}"
            self._set_meta("daily_round_count", str(count))
            self._set_meta("daily_round", self._daily_round)
            self._set_meta("daily_round_started", now.isoformat())
        elif scope in MANUAL_ROUND_SCOPES:
            base = period_key(scope, today or date.today())
            old_base, n, _ = self._manual_rounds[scope]
            n = n + 1 if old_base == base else 1
            self._manual_rounds[scope] = (base, n, now)
            self._set_meta(f"round_{scope.value}", f"{base}|{n}")
            self._set_meta(f"round_{scope.value}_started", now.isoformat())
        else:
            raise ValueError(f"{scope.label}任务是一次性的，没有「轮」")
        self.conn.commit()

    def round_started(self, scope: Scope, today: date | None = None) -> datetime | None:
        """这一轮是什么时候手动开始的。每周 / 每年这个周期里没手动重来过就是 None。"""
        if scope is Scope.DAILY:
            row = self.conn.execute(
                "SELECT value FROM meta WHERE key = 'daily_round_started'"
            ).fetchone()
            return _dt(row["value"]) if row else None
        base, n, started = self._manual_rounds.get(scope, ("", 0, None))
        if n and base == period_key(scope, today or date.today()):
            return started
        return None

    def _set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?)"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    def _period(self, scope: Scope, today: date, day: date | None = None) -> str:
        key = period_key(scope, today, day, daily_round=self._daily_round)
        if scope in MANUAL_ROUND_SCOPES:
            base, n, _ = self._manual_rounds[scope]
            if n and base == key:  # 这个日历周期里手动重来过
                key = f"{key}#{n}"
        return key

    # ---------- 增删改 ----------

    def add(self, title: str, scope: Scope, day: date | None = None) -> Todo:
        """新任务排在这个分组最后。"""
        todo = Todo(title=title.strip(), scope=scope, day=day or date.today())
        cur = self.conn.execute(
            "INSERT INTO todos (title, scope, day, created_at, position) VALUES"
            " (?, ?, ?, ?, (SELECT COALESCE(MAX(position), -1) + 1 FROM todos WHERE scope = ?))",
            (
                todo.title,
                scope.value,
                todo.day.isoformat(),
                todo.created_at.isoformat(),
                scope.value,
            ),
        )
        self.conn.commit()
        todo.id = cur.lastrowid
        return todo

    def move(self, todo: Todo, offset: int, today: date | None = None) -> bool:
        """在分组里上移（-1）/ 下移（+1）一位。到头了移不动返回 False。

        「一位」按界面上看得见的顺序算 —— 当天分组里藏着以前做完的任务，
        跟它们换位置的话，按了等于没反应。
        """
        visible = [t.id for t in self.todos(todo.scope, today)]
        if todo.id not in visible:
            return False
        i = visible.index(todo.id)
        j = i + offset
        if not 0 <= j < len(visible):
            return False
        # 先把整个分组的位置理成 0..n-1（旧数据可能有重复），再交换这两个
        rows = self.conn.execute(
            "SELECT id FROM todos WHERE scope = ? ORDER BY position, id",
            (todo.scope.value,),
        ).fetchall()
        order = [r["id"] for r in rows]
        a, b = order.index(visible[i]), order.index(visible[j])
        order[a], order[b] = order[b], order[a]
        self.conn.executemany(
            "UPDATE todos SET position = ? WHERE id = ?",
            [(pos, tid) for pos, tid in enumerate(order)],
        )
        self.conn.commit()
        return True

    def delete(self, todo_id: int) -> None:
        self.conn.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
        self.conn.commit()

    def set_done(
        self,
        todo: Todo,
        done: bool,
        today: date | None = None,
        at: datetime | None = None,
    ) -> None:
        """at：什么时候做完的，默认现在（测试里用来造历史）。"""
        period = self._period(todo.scope, today or date.today(), todo.day)
        if done:
            stamp = (at or datetime.now()).isoformat()
            cur = self.conn.execute(
                "INSERT OR IGNORE INTO todo_done (todo_id, period, done_at)"
                " VALUES (?,?,?)",
                (todo.id, period, stamp),
            )
            if cur.rowcount:  # 重复勾不重复记
                self._log("task", todo.id, period, todo.title, todo.scope, stamp)
        else:
            cur = self.conn.execute(
                "DELETE FROM todo_done WHERE todo_id = ? AND period = ?",
                (todo.id, period),
            )
            if cur.rowcount:
                self.conn.execute(
                    "DELETE FROM activity WHERE kind = 'task' AND ref_id = ? AND period = ?",
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
            "SELECT * FROM todos WHERE scope = ? ORDER BY position, id", (scope.value,)
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
            (todo.id, self._period(todo.scope, today, todo.day)),
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
        period = self._period(scope, today)
        fresh = []
        for reward in self.rewards(scope, today):
            if reward.earned or not reached(done, total, reward.percent):
                continue
            stamp = datetime.now().isoformat()
            cur = self.conn.execute(
                "INSERT OR IGNORE INTO reward_claims (reward_id, period, claimed_at)"
                " VALUES (?,?,?)",
                (reward.id, period, stamp),
            )
            if cur.rowcount:
                self._log("reward", reward.id, period, reward.text, reward.scope, stamp)
            reward.earned = True
            fresh.append(reward)
        self.conn.commit()
        return fresh

    def _claimed(self, reward: Reward, today: date) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM reward_claims WHERE reward_id = ? AND period = ?",
            (reward.id, self._period(reward.scope, today)),
        ).fetchone()
        return row is not None

    # ---------- 活动记录 ----------

    def _log(self, kind, ref_id, period, title, scope, at: str) -> None:
        self.conn.execute(
            "INSERT INTO activity (kind, ref_id, period, title, scope, at)"
            " VALUES (?,?,?,?,?,?)",
            (kind, ref_id, period, title, scope.value if scope else None, at),
        )

    def activity_counts(self, start: date, end: date) -> dict[date, int]:
        """[start, end] 里每天做完几件事（只数任务，不数奖励）。"""
        rows = self.conn.execute(
            "SELECT substr(at, 1, 10) AS d, COUNT(*) AS n FROM activity"
            " WHERE kind = 'task' AND at >= ? AND at < ? GROUP BY d",
            (start.isoformat(), (end + timedelta(days=1)).isoformat()),
        ).fetchall()
        return {date.fromisoformat(r["d"]): r["n"] for r in rows}

    def activity_days(self) -> set[date]:
        """所有做过事的日子，算连续天数用。"""
        rows = self.conn.execute(
            "SELECT DISTINCT substr(at, 1, 10) AS d FROM activity WHERE kind = 'task'"
        ).fetchall()
        return {date.fromisoformat(r["d"]) for r in rows}

    def activity_on(self, day: date) -> list[Activity]:
        rows = self.conn.execute(
            "SELECT * FROM activity WHERE at >= ? AND at < ? ORDER BY at, id",
            (day.isoformat(), (day + timedelta(days=1)).isoformat()),
        ).fetchall()
        return [
            Activity(
                kind=r["kind"],
                title=r["title"],
                scope=Scope(r["scope"]) if r["scope"] else None,
                at=_dt(r["at"]),
            )
            for r in rows
        ]

    def activity_years(self, today: date | None = None) -> list[int]:
        """有记录的年份（新的在前），今年总在里面。"""
        today = today or date.today()
        rows = self.conn.execute(
            "SELECT DISTINCT substr(at, 1, 4) AS y FROM activity"
        ).fetchall()
        years = {int(r["y"]) for r in rows} | {today.year}
        return sorted(years, reverse=True)

    def _backfill_activity(self) -> None:
        """活动记录是 0.5 才有的。之前的完成记录、奖励、最早那版做完的任务，补一次进来。"""
        if self.conn.execute(
            "SELECT 1 FROM meta WHERE key = 'activity_backfilled'"
        ).fetchone():
            return
        self.conn.execute(
            "INSERT INTO activity (kind, ref_id, period, title, scope, at)"
            " SELECT 'task', d.todo_id, d.period, t.title, t.scope, d.done_at"
            " FROM todo_done d JOIN todos t ON t.id = d.todo_id"
        )
        self.conn.execute(
            "INSERT INTO activity (kind, ref_id, period, title, scope, at)"
            " SELECT 'reward', c.reward_id, c.period, r.text, r.scope, c.claimed_at"
            " FROM reward_claims c JOIN rewards r ON r.id = c.reward_id"
        )
        has_legacy = self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'tasks'"
        ).fetchone()
        if has_legacy:
            columns = {r["name"] for r in self.conn.execute("PRAGMA table_info(tasks)")}
            if {"title", "status", "done_at"} <= columns:
                self.conn.execute(
                    "INSERT INTO activity (kind, ref_id, period, title, scope, at)"
                    " SELECT 'task', NULL, NULL, title, NULL, done_at FROM tasks"
                    " WHERE status = 'done' AND done_at IS NOT NULL"
                )
        self._set_meta("activity_backfilled", datetime.now().isoformat())

    # ---------- 旧版本数据 ----------

    def _add_position_column(self) -> None:
        """0.8 之前的库没有 position：补上，按原来的顺序（id）排。"""
        columns = {r["name"] for r in self.conn.execute("PRAGMA table_info(todos)")}
        if "position" not in columns:
            self.conn.execute(
                "ALTER TABLE todos ADD COLUMN position INTEGER NOT NULL DEFAULT 0"
            )
            self.conn.execute("UPDATE todos SET position = id")

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
