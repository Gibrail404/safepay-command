from __future__ import annotations
from sqlalchemy import Boolean, Index, Integer, String, Text, UniqueConstraint, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"
    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(64))
    payload: Mapped[str] = mapped_column(Text)          # canonical JSON, exactly the string that was hashed
    ts: Mapped[str] = mapped_column(String(40))
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))
    __table_args__ = (Index("ix_ledger_tenant_seq", "tenant", "seq"),)


class LedgerHead(Base):
    """One row per tenant: the hash of the newest entry and how many entries exist. Locked while appending."""
    __tablename__ = "ledger_heads"
    tenant: Mapped[str] = mapped_column(String(64), primary_key=True)
    head_hash: Mapped[str] = mapped_column(String(64))
    length: Mapped[int] = mapped_column(Integer)


class PolicyRow(Base):
    """Content-addressed policy snapshots: version is the hash of the rules, so a decision can always be replayed."""
    __tablename__ = "policies"
    version: Mapped[str] = mapped_column(String(64), primary_key=True)
    content: Mapped[str] = mapped_column(Text)


class DecisionRow(Base):
    __tablename__ = "decisions"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    tenant: Mapped[str] = mapped_column(String(64), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128))
    request_hash: Mapped[str] = mapped_column(String(64))
    request: Mapped[str] = mapped_column(Text)
    response: Mapped[str] = mapped_column(Text)
    policy_version: Mapped[str] = mapped_column(String(64))
    __table_args__ = (UniqueConstraint("tenant", "idempotency_key", name="uq_decision_idem"),)


class ToolCallRow(Base):
    __tablename__ = "tool_calls"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant: Mapped[str] = mapped_column(String(64), index=True)
    tool: Mapped[str] = mapped_column(String(64))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    args_hash: Mapped[str] = mapped_column(String(64))
    result: Mapped[str] = mapped_column(Text)
    __table_args__ = (UniqueConstraint("tenant", "tool", "idempotency_key", name="uq_toolcall_idem"),)


class ApprovalRow(Base):
    __tablename__ = "approvals"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    tenant: Mapped[str] = mapped_column(String(64), index=True)
    tool: Mapped[str] = mapped_column(String(64))
    args_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))      # pending | approved | rejected | used
    decided_by: Mapped[str | None] = mapped_column(String(64), nullable=True)


def make_engine(url: str = "sqlite+pysqlite:///:memory:"):
    if url.startswith("sqlite") and ":memory:" in url:
        return create_engine(url, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    return create_engine(url, pool_pre_ping=True)


def init_db(engine) -> sessionmaker[Session]:
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)
