from datetime import date, datetime

from sqlalchemy import (BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer,
                        LargeBinary, String, Text, UniqueConstraint, func, text)
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

# 课程 id 由课程清单决定（app/catalog.py ID_RE），库里只约束格式；见基线迁移 0001_baseline
COURSE_CHECK = "course ~ '^[a-z][a-z0-9_]{0,15}$'"


def _user_fk():
    return mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)


def _now():
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)  # 存储前 trim + 小写
    pw_hash: Mapped[str] = mapped_column(Text, nullable=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _now()


class Session(Base):
    __tablename__ = "sessions"
    id_hash: Mapped[bytes] = mapped_column(LargeBinary, primary_key=True)  # SHA-256(cookie)
    user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    csrf_token: Mapped[str] = mapped_column(Text, nullable=False)
    user_agent: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _now()
    last_seen_at: Mapped[datetime] = _now()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class PasswordReset(Base):
    __tablename__ = "password_resets"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = _user_fk()
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, unique=True)
    created_at: Mapped[datetime] = _now()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    request_ip: Mapped[str | None] = mapped_column(INET)
    __table_args__ = (Index("ix_password_resets_unused", "user_id", postgresql_where=text("used_at IS NULL")),)


class ProgressItem(Base):
    __tablename__ = "progress_items"
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    course: Mapped[str] = mapped_column(Text, primary_key=True)
    item_id: Mapped[str] = mapped_column(Text, primary_key=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    amt: Mapped[int | None] = mapped_column(Integer)
    rev: Mapped[bool | None] = mapped_column(Boolean)
    wrong: Mapped[int | None] = mapped_column(Integer)
    fix: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    first_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = _now()
    source: Mapped[str] = mapped_column(Text, nullable=False)
    __table_args__ = (
        CheckConstraint(COURSE_CHECK, name="ck_progress_items_course"),
        CheckConstraint("kind IN ('xp','done','solved','rec')", name="ck_progress_items_kind"),
        CheckConstraint("amt IS NULL OR amt >= 0", name="ck_progress_items_amt"),
        CheckConstraint("source IN ('event','import')", name="ck_progress_items_source"),
        Index("ix_progress_items_user_course_updated", "user_id", "course", "updated_at"),
    )


class ProgressEvent(Base):
    __tablename__ = "progress_events"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = _user_fk()
    client_event_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    course: Mapped[str] = mapped_column(Text, nullable=False)
    item_id: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    amt: Mapped[int | None] = mapped_column(Integer)  # 上报值（截断前）
    payload: Mapped[dict | None] = mapped_column(JSONB)
    client_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    local_day: Mapped[date | None] = mapped_column(Date)
    received_at: Mapped[datetime] = _now()
    status: Mapped[str] = mapped_column(Text, nullable=False)
    __table_args__ = (
        UniqueConstraint("user_id", "client_event_id", name="uq_progress_events_user_cid"),
        Index("ix_progress_events_user_received", "user_id", text("received_at DESC")),
        Index("ix_progress_events_received", "received_at"),
    )


class BadgeAward(Base):
    __tablename__ = "badge_awards"
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    course: Mapped[str] = mapped_column(Text, primary_key=True)
    badge_id: Mapped[str] = mapped_column(Text, primary_key=True)
    awarded_on: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = _now()
    __table_args__ = (CheckConstraint(COURSE_CHECK, name="ck_badge_awards_course"),)


class ActivityDay(Base):
    __tablename__ = "activity_days"
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    course: Mapped[str] = mapped_column(Text, primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    __table_args__ = (CheckConstraint(COURSE_CHECK, name="ck_activity_days_course"),
                      Index("ix_activity_days_user_day", "user_id", "day"))


class Import(Base):
    __tablename__ = "imports"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = _user_fk()
    course: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(64))
    result: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = _now()
    __table_args__ = (UniqueConstraint("user_id", "idempotency_key", name="uq_imports_user_key"),
                      Index("ix_imports_user_created", "user_id", "created_at"))


class ProgressReset(Base):
    __tablename__ = "progress_resets"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = _user_fk()
    course: Mapped[str] = mapped_column(Text, nullable=False)
    reset_at: Mapped[datetime] = _now()
    __table_args__ = (Index("ix_progress_resets_user_course", "user_id", "course"),)


class ContentVersion(Base):
    __tablename__ = "content_versions"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    course: Mapped[str] = mapped_column(Text, nullable=False)
    source_commit: Mapped[str] = mapped_column(Text, nullable=False)
    total: Mapped[int] = mapped_column(Integer, nullable=False)
    ids_hash: Mapped[str] = mapped_column(Text, nullable=False)
    imported_at: Mapped[datetime] = _now()
