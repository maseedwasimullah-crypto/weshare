import logging
import secrets
import smtplib
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from threading import Lock

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from .config import settings
from .database import SessionLocal, engine
from .models import AuditLog, Base, Comment, Moderation, Post, User
from .moderation import ContentRejected, moderate, validate_text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("weshare.api")

POST_MAX_LENGTH = 1000
COMMENT_MAX_LENGTH = 100
MAX_LOGIN_ATTEMPTS = 10
LOGIN_WINDOW_SECONDS = 900


@asynccontextmanager
async def lifespan(app: FastAPI):
    if len(settings.secret_key) < 32:
        raise RuntimeError(
            "SECRET_KEY must be at least 32 characters. On Render set it in "
            "the service environment variables, or use the Blueprint value "
            "'SECRET_KEY: generateValue: true'."
        )
    if not settings.frontend_origins:
        raise RuntimeError(
            "FRONTEND_ORIGIN must contain the exact origin of the frontend, "
            "for example https://your-app.vercel.app"
        )
    Base.metadata.create_all(engine)
    logger.info("WeShare API ready")
    yield


app = FastAPI(title="WeShare! API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.frontend_origins,
    # Optional regular expression for preview deployments, for example
    # r"https://weshare-.*\.vercel\.app". A regex is only used when it is set
    # explicitly, so the default policy stays an exact origin match.
    allow_origin_regex=settings.frontend_origin_regex or None,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

security = HTTPBearer(auto_error=False)
hasher = PasswordHasher()
login_attempts: dict[str, deque] = defaultdict(deque)
login_lock = Lock()
DUMMY_HASH = hasher.hash("we-share-timing-equalizer")


def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def make_token(user, purpose: str = "session") -> str:
    minutes = settings.access_token_minutes if purpose == "session" else 1440
    exp = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    payload = {"sub": str(user.id), "purpose": purpose, "iat": datetime.now(timezone.utc), "exp": exp}
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def current(
    creds: HTTPAuthorizationCredentials | None = Depends(security),
    session: Session = Depends(db),
):
    if not creds:
        raise HTTPException(401, "Authentication required.")
    try:
        payload = jwt.decode(creds.credentials, settings.secret_key, algorithms=["HS256"])
        if payload.get("purpose") != "session":
            raise ValueError("wrong token purpose")
        user = session.get(User, int(payload["sub"]))
    except (jwt.PyJWTError, KeyError, TypeError, ValueError):
        raise HTTPException(401, "Invalid or expired session.")
    if not user or not user.is_active:
        raise HTTPException(401, "Invalid or expired session.")
    return user


def admin(user: User = Depends(current)):
    if user.role != "admin":
        raise HTTPException(403, "Administrator access required.")
    return user


def verified(user: User = Depends(current)):
    if not user.email_verified:
        raise HTTPException(403, "Verify your email before posting or commenting.")
    return user


class Registration(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    confirm_password: str = Field(min_length=12, max_length=128)

    @field_validator("password")
    @classmethod
    def strong(cls, value: str) -> str:
        has_lower = any(c.islower() for c in value)
        has_upper = any(c.isupper() for c in value)
        has_digit = any(c.isdigit() for c in value)
        has_symbol = any(not c.isalnum() for c in value)
        if not (has_lower and has_upper and has_digit and has_symbol):
            raise ValueError(
                "Password must contain uppercase, lowercase, number, and symbol."
            )
        return value


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TextBody(BaseModel):
    content: str = Field(max_length=5000)


class VerifyBody(BaseModel):
    token: str = Field(min_length=1, max_length=4096)


class StatusBody(BaseModel):
    is_active: bool


def log_moderation(session, kind: str, decision: str, reason: str, text: str) -> None:
    session.add(
        Moderation(
            content_type=kind,
            decision=decision,
            reason=reason[:240],
            content_excerpt=text[:1000],
        )
    )


def unique_username(session, email: str) -> str:
    prefix = email.split("@", 1)[0][:65] or "user"
    candidate = prefix
    if session.scalar(select(User.id).where(User.username == candidate)):
        candidate = f"{prefix[:54]}_{secrets.token_hex(4)}"
    return candidate


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/auth/register", status_code=201)
def register(body: Registration, session: Session = Depends(db)):
    if body.password != body.confirm_password:
        raise HTTPException(422, "Passwords do not match.")
    email = str(body.email).lower()
    if session.scalar(select(User).where(func.lower(User.email) == email)):
        raise HTTPException(409, "An account with this email already exists.")
    username = unique_username(session, email)
    user = User(
        email=email,
        username=username,
        password_hash=hasher.hash(body.password),
        email_verified=False,
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    verification_token = make_token(user, "verify")
    sent = False
    if settings.smtp_configured:
        message = EmailMessage()
        message["Subject"] = "Verify your WeShare! account"
        message["From"] = settings.email_from
        message["To"] = email
        message.set_content(
            "Use this verification token to activate your WeShare! account:\n\n"
            + verification_token
        )
        try:
            with smtplib.SMTP(settings.email_host, settings.email_port, timeout=10) as smtp:
                if settings.email_use_tls:
                    smtp.starttls()
                if settings.email_user:
                    smtp.login(settings.email_user, settings.email_password)
                smtp.send_message(message)
            sent = True
        except Exception:
            logger.exception("Verification email could not be sent to %s", email)
            sent = False

    if sent:
        message_text = "Check your email to verify your account."
    else:
        message_text = (
            "Account created, but the verification email was not sent. "
            "Configure SMTP, or use the verification token returned below."
        )

    payload = {
        "message": message_text,
        "username": username,
        "verification_email_sent": sent,
    }
    if not sent and settings.exposes_verification_token:
        payload["verification_token"] = verification_token
    return payload


@app.post("/api/auth/verify")
def verify(body: VerifyBody, session: Session = Depends(db)):
    try:
        payload = jwt.decode(body.token, settings.secret_key, algorithms=["HS256"])
        if payload.get("purpose") != "verify":
            raise ValueError("wrong token purpose")
        user = session.get(User, int(payload["sub"]))
    except (jwt.PyJWTError, KeyError, TypeError, ValueError):
        raise HTTPException(400, "Invalid or expired verification token.")
    if not user:
        raise HTTPException(400, "Invalid or expired verification token.")
    user.email_verified = True
    session.commit()
    return {"message": "Email verified."}


@app.post("/api/auth/login")
def login(body: Credentials, response: Response, session: Session = Depends(db)):
    key = str(body.email).lower()
    now = time.monotonic()
    with login_lock:
        attempts = login_attempts[key]
        while attempts and now - attempts[0] > LOGIN_WINDOW_SECONDS:
            attempts.popleft()
        if len(attempts) >= MAX_LOGIN_ATTEMPTS:
            raise HTTPException(429, "Too many login attempts. Try again later.")
        attempts.append(now)

    user = session.scalar(select(User).where(func.lower(User.email) == key))
    stored_hash = user.password_hash if user else DUMMY_HASH
    try:
        ok = bool(hasher.verify(stored_hash, body.password))
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        ok = False
    if not user or not ok:
        raise HTTPException(401, "Email or password is incorrect.")
    if not user.is_active:
        raise HTTPException(403, "This account has been deactivated.")

    token = make_token(user)
    response.set_cookie(
        "weshare_session",
        token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.access_token_minutes * 60,
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "email_verified": user.email_verified,
        },
    }


@app.post("/api/auth/logout")
def logout(response: Response):
    response.delete_cookie("weshare_session", path="/")
    return {"message": "Logged out."}


@app.get("/api/auth/me")
def me(user: User = Depends(current)):
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role,
        "email_verified": user.email_verified,
    }


@app.get("/api/feed")
def feed(limit: int = 20, offset: int = 0, session: Session = Depends(db)):
    limit = max(1, min(limit, 50))
    offset = max(0, offset)
    posts = (
        session.scalars(
            select(Post)
            .options(joinedload(Post.author))
            .order_by(Post.created_at.desc(), Post.id.desc())
            .offset(offset)
            .limit(limit)
        )
        .unique()
        .all()
    )
    items = []
    for post in posts:
        count = session.scalar(select(func.count(Comment.id)).where(Comment.post_id == post.id))
        comments = (
            session.scalars(
                select(Comment)
                .options(joinedload(Comment.author))
                .where(Comment.post_id == post.id)
                .order_by(Comment.created_at.asc(), Comment.id.asc())
                .limit(50)
            )
            .unique()
            .all()
        )
        items.append(
            {
                "id": post.id,
                "username": post.author.username,
                "content": post.content,
                "created_at": post.created_at,
                "comment_count": count,
                "comments": [
                    {
                        "id": comment.id,
                        "username": comment.author.username,
                        "content": comment.content,
                        "created_at": comment.created_at,
                    }
                    for comment in comments
                ],
            }
        )
    return {"items": items, "limit": limit, "offset": offset, "has_more": len(posts) == limit}


@app.post("/api/posts", status_code=201)
def create_post(body: TextBody, user: User = Depends(verified), session: Session = Depends(db)):
    try:
        validate_text(body.content, POST_MAX_LENGTH)
        moderate(body.content)
    except ContentRejected as exc:
        log_moderation(session, "post", "rejected", str(exc), body.content)
        session.commit()
        raise HTTPException(422, str(exc))
    post = Post(user_id=user.id, content=body.content)
    session.add(post)
    log_moderation(session, "post", "approved", "Passed configured checks.", body.content)
    session.commit()
    session.refresh(post)
    return {
        "id": post.id,
        "username": user.username,
        "content": post.content,
        "created_at": post.created_at,
        "comment_count": 0,
        "comments": [],
    }


@app.post("/api/posts/{post_id}/comments", status_code=201)
def create_comment(
    post_id: int,
    body: TextBody,
    user: User = Depends(verified),
    session: Session = Depends(db),
):
    if not session.get(Post, post_id):
        raise HTTPException(404, "Post not found.")
    try:
        validate_text(body.content, COMMENT_MAX_LENGTH)
        moderate(body.content)
    except ContentRejected as exc:
        log_moderation(session, "comment", "rejected", str(exc), body.content)
        session.commit()
        raise HTTPException(422, str(exc))
    comment = Comment(post_id=post_id, user_id=user.id, content=body.content)
    session.add(comment)
    log_moderation(session, "comment", "approved", "Passed configured checks.", body.content)
    session.commit()
    session.refresh(comment)
    return {
        "id": comment.id,
        "username": user.username,
        "content": comment.content,
        "created_at": comment.created_at,
    }


@app.get("/api/admin/stats")
def stats(admin_user: User = Depends(admin), session: Session = Depends(db)):
    return {
        "users": session.scalar(select(func.count(User.id))),
        "active_users": session.scalar(
            select(func.count(User.id)).where(User.is_active == True)  # noqa: E712
        ),
        "posts": session.scalar(select(func.count(Post.id))),
        "comments": session.scalar(select(func.count(Comment.id))),
    }


@app.get("/api/admin/users")
def admin_users(
    search: str = "",
    limit: int = 50,
    offset: int = 0,
    admin_user: User = Depends(admin),
    session: Session = Depends(db),
):
    query = select(User)
    if search:
        pattern = "%" + search.strip() + "%"
        query = query.where(
            or_(User.email.ilike(pattern), User.username.ilike(pattern))
        )
    query = query.order_by(User.created_at.desc()).offset(max(0, offset)).limit(
        min(max(1, limit), 100)
    )
    return [
        {
            "id": user.id,
            "email": user.email,
            "username": user.username,
            "email_verified": user.email_verified,
            "role": user.role,
            "is_active": user.is_active,
            "created_at": user.created_at,
        }
        for user in session.scalars(query).all()
    ]


@app.patch("/api/admin/users/{user_id}")
def set_status(
    user_id: int,
    body: StatusBody,
    admin_user: User = Depends(admin),
    session: Session = Depends(db),
):
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found.")
    if user.id == admin_user.id and not body.is_active:
        raise HTTPException(400, "Cannot deactivate your own account.")
    if user.role == "admin" and user.id != admin_user.id:
        raise HTTPException(400, "Cannot change the status of another administrator.")
    user.is_active = body.is_active
    session.add(
        AuditLog(
            admin_id=admin_user.id,
            action="user_status_changed",
            affected_type="user",
            affected_id=str(user.id),
        )
    )
    session.commit()
    return {"id": user.id, "is_active": user.is_active}


@app.delete("/api/admin/users/{user_id}", status_code=204)
def delete_user(
    user_id: int,
    admin_user: User = Depends(admin),
    session: Session = Depends(db),
):
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found.")
    if user.id == admin_user.id:
        raise HTTPException(400, "Cannot delete your own account.")
    if user.role == "admin":
        raise HTTPException(400, "Cannot delete another administrator.")
    session.add(
        AuditLog(
            admin_id=admin_user.id,
            action="user_deleted",
            affected_type="user",
            affected_id=str(user.id),
        )
    )
    session.delete(user)
    session.commit()
    return Response(status_code=204)


@app.get("/api/admin/content")
def admin_content(
    limit: int = 100,
    admin_user: User = Depends(admin),
    session: Session = Depends(db),
):
    n = min(max(1, limit), 200)
    posts = (
        session.scalars(
            select(Post).options(joinedload(Post.author)).order_by(Post.created_at.desc()).limit(n)
        )
        .unique()
        .all()
    )
    comments = (
        session.scalars(
            select(Comment)
            .options(joinedload(Comment.author))
            .order_by(Comment.created_at.desc())
            .limit(n)
        )
        .unique()
        .all()
    )
    return {
        "posts": [
            {
                "id": post.id,
                "username": post.author.username,
                "content": post.content,
                "created_at": post.created_at,
            }
            for post in posts
        ],
        "comments": [
            {
                "id": comment.id,
                "username": comment.author.username,
                "content": comment.content,
                "created_at": comment.created_at,
                "post_id": comment.post_id,
            }
            for comment in comments
        ],
    }


@app.delete("/api/admin/posts/{post_id}", status_code=204)
def delete_post(
    post_id: int,
    admin_user: User = Depends(admin),
    session: Session = Depends(db),
):
    post = session.get(Post, post_id)
    if not post:
        raise HTTPException(404, "Post not found.")
    session.add(
        AuditLog(
            admin_id=admin_user.id,
            action="post_deleted",
            affected_type="post",
            affected_id=str(post.id),
        )
    )
    session.delete(post)
    session.commit()
    return Response(status_code=204)


@app.delete("/api/admin/comments/{comment_id}", status_code=204)
def delete_comment(
    comment_id: int,
    admin_user: User = Depends(admin),
    session: Session = Depends(db),
):
    comment = session.get(Comment, comment_id)
    if not comment:
        raise HTTPException(404, "Comment not found.")
    session.add(
        AuditLog(
            admin_id=admin_user.id,
            action="comment_deleted",
            affected_type="comment",
            affected_id=str(comment.id),
        )
    )
    session.delete(comment)
    session.commit()
    return Response(status_code=204)


@app.get("/api/admin/moderation")
def moderation_history(
    limit: int = 100,
    admin_user: User = Depends(admin),
    session: Session = Depends(db),
):
    rows = (
        session.scalars(
            select(Moderation).order_by(Moderation.created_at.desc()).limit(min(max(limit, 1), 200))
        )
        .all()
    )
    return [
        {
            "id": row.id,
            "content_type": row.content_type,
            "decision": row.decision,
            "reason": row.reason,
            "content_excerpt": row.content_excerpt,
            "created_at": row.created_at,
        }
        for row in rows
    ]
