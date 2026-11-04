"""Daily LLM budget kept in the database. Same interface as the in-memory Budget (reserve, add_tokens), but the daily counters are shared by all processes
and survive restarts. The decision to allow a call is one conditional UPDATE, so simultaneous callers cannot all slip under the cap. The per-run cap stays in memory:
it only protects a single request from looping, and runs are short-lived."""
from __future__ import annotations
import threading, time
from datetime import datetime, timezone
from typing import Callable
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from ..db import LlmUsageRow


class DbBudget:
    def __init__(self, sf: sessionmaker[Session], max_requests_per_day: int = 400, max_tokens_per_day: int = 400_000, max_requests_per_run: int = 12, clock: Callable[[], float] = time.time):
        self.sf, self.max_requests_per_day, self.max_tokens_per_day, self.max_requests_per_run, self.clock = sf, max_requests_per_day, max_tokens_per_day, max_requests_per_run, clock
        self._runs: dict[str, int] = {}
        self._lock = threading.Lock()

    def _day(self) -> str:
        return datetime.fromtimestamp(self.clock(), timezone.utc).strftime("%Y-%m-%d")

    def _ensure_row(self, day: str) -> None:
        with self.sf.begin() as s:
            if s.get(LlmUsageRow, day) is None:
                s.add(LlmUsageRow(day=day, requests=0, tokens=0))
                try:
                    s.flush()
                except IntegrityError:            # another process created it first
                    s.rollback()

    def reserve(self, run_id: str) -> str | None:
        with self._lock:
            if self._runs.get(run_id, 0) >= self.max_requests_per_run:
                return "per-run request cap reached"
        day = self._day()
        self._ensure_row(day)
        with self.sf.begin() as s:
            won = s.execute(update(LlmUsageRow).where(LlmUsageRow.day == day, LlmUsageRow.requests < self.max_requests_per_day, LlmUsageRow.tokens < self.max_tokens_per_day)
                            .values(requests=LlmUsageRow.requests + 1)).rowcount
            if won != 1:
                row = s.scalar(select(LlmUsageRow).where(LlmUsageRow.day == day))
                return "daily request cap reached" if row and row.requests >= self.max_requests_per_day else "daily token cap reached"
        with self._lock:
            self._runs[run_id] = self._runs.get(run_id, 0) + 1
            if len(self._runs) > 10_000:           # bounded memory
                self._runs.clear()
        return None

    def add_tokens(self, n: int | None) -> None:
        if not n:
            return
        day = self._day()
        self._ensure_row(day)
        with self.sf.begin() as s:
            s.execute(update(LlmUsageRow).where(LlmUsageRow.day == day).values(tokens=LlmUsageRow.tokens + n))
