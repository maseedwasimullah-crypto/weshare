from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase): pass

def now(): return datetime.now(timezone.utc)

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="user", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)
    posts: Mapped[list["Post"]] = relationship(back_populates="author", cascade="all, delete-orphan")
    comments: Mapped[list["Comment"]] = relationship(back_populates="author", cascade="all, delete-orphan")

class Post(Base):
    __tablename__ = "posts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    content: Mapped[str] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    author: Mapped[User] = relationship(back_populates="posts")
    comments: Mapped[list["Comment"]] = relationship(back_populates="post", cascade="all, delete-orphan")
    __table_args__ = (Index("ix_posts_created_id", "created_at", "id"),)

class Comment(Base):
    __tablename__ = "comments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    content: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    author: Mapped[User] = relationship(back_populates="comments")
    post: Mapped[Post] = relationship(back_populates="comments")
    __table_args__ = (Index("ix_comments_post_created", "post_id", "created_at"),)

class Moderation(Base):
    __tablename__ = "moderation_decisions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    content_type: Mapped[str] = mapped_column(String(20))
    decision: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(String(240))
    content_excerpt: Mapped[str] = mapped_column(String(1000), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    admin_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(80))
    affected_type: Mapped[str] = mapped_column(String(40))
    affected_id: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
