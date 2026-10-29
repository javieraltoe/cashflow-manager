"""Login, rotación de refresh tokens y logout."""

from datetime import timedelta

from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.rate_limit import LoginRateLimiter
from app.core.security import (
    create_access_token,
    hash_password,
    hash_refresh_token,
    needs_rehash,
    new_refresh_token,
    verify_password,
)
from app.core.timeutils import utcnow
from app.models import RefreshToken, User
from app.schemas.auth import TokenOut
from app.services.users import get_by_email, revoke_all_refresh_tokens

_settings = get_settings()
login_limiter = LoginRateLimiter(
    max_attempts=_settings.login_max_attempts,
    window_seconds=_settings.login_lockout_minutes * 60,
)


def _invalid_credentials() -> AppError:
    return AppError(
        "invalid_credentials", "Email o contraseña incorrectos", status.HTTP_401_UNAUTHORIZED
    )


def _invalid_refresh() -> AppError:
    return AppError(
        "invalid_refresh_token", "Sesión vencida: volvé a ingresar", status.HTTP_401_UNAUTHORIZED
    )


def authenticate(db: Session, email: str, password: str) -> User:
    key = email.strip().lower()
    if login_limiter.is_blocked(key):
        raise AppError(
            "too_many_attempts",
            "Demasiados intentos fallidos. Probá de nuevo en unos minutos.",
            status.HTTP_429_TOO_MANY_REQUESTS,
        )
    user = get_by_email(db, key)
    # verify_password se ejecuta siempre (también si el usuario no existe).
    password_ok = verify_password(password, user.password_hash if user else None)
    if not user or not password_ok or not user.is_active:
        login_limiter.register_failure(key)
        raise _invalid_credentials()
    login_limiter.reset(key)
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    return user


def issue_tokens(db: Session, user: User) -> TokenOut:
    access, expires_in = create_access_token(user.id, user.role)
    raw, token_hash = new_refresh_token()
    rt = RefreshToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=utcnow() + timedelta(days=get_settings().refresh_token_days),
    )
    db.add(rt)
    db.commit()
    return TokenOut(access_token=access, refresh_token=raw, expires_in=expires_in)


def _find(db: Session, raw: str, lock: bool = False) -> RefreshToken | None:
    stmt = select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(raw))
    if lock:
        stmt = stmt.with_for_update()
    return db.scalar(stmt)


def refresh(db: Session, raw: str) -> TokenOut:
    rt = _find(db, raw, lock=True)
    if rt is None:
        raise _invalid_refresh()
    if rt.revoked_at is not None:
        # Reutilización de un token ya rotado: posible robo -> se cierran todas las sesiones.
        if rt.replaced_by_id is not None:
            revoke_all_refresh_tokens(db, rt.user_id)
            db.commit()
        raise _invalid_refresh()
    if rt.expires_at <= utcnow():
        raise _invalid_refresh()
    user = db.get(User, rt.user_id)
    if user is None or not user.is_active:
        raise _invalid_refresh()

    access, expires_in = create_access_token(user.id, user.role)
    new_raw, new_hash = new_refresh_token()
    new_rt = RefreshToken(
        user_id=user.id,
        token_hash=new_hash,
        expires_at=utcnow() + timedelta(days=get_settings().refresh_token_days),
    )
    db.add(new_rt)
    db.flush()
    rt.revoked_at = utcnow()
    rt.replaced_by_id = new_rt.id
    db.commit()
    return TokenOut(access_token=access, refresh_token=new_raw, expires_in=expires_in)


def logout(db: Session, raw: str) -> None:
    rt = _find(db, raw)
    if rt is not None and rt.revoked_at is None:
        rt.revoked_at = utcnow()
        db.commit()
