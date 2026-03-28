from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    hash_token,
    normalize_email,
    verify_password,
)
from app.models.creator import Creator
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.auth import GuestLoginRequest, LoginRequest, RefreshRequest, SignupRequest


class AuthService:
    @staticmethod
    async def signup(db: AsyncSession, payload: SignupRequest) -> dict:
        email = normalize_email(str(payload.email))
        if email is None:
            raise HTTPException(status_code=400, detail="Valid email is required")

        existing = await db.execute(select(User).where(User.email == email))
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(status_code=409, detail="Email already registered")

        user = User(
            email=email,
            password_hash=hash_password(payload.password),
            display_name=payload.display_name,
            role=payload.role,
            is_guest=False,
            is_active=True,
            is_email_verified=False,
        )
        db.add(user)
        await db.flush()

        if payload.role == "creator":
            db.add(Creator(
                user_id=user.id,
                display_name=user.display_name,
                is_active=True,
                subscriber_count=0,
                post_count=0,
                total_likes=0,
            ))
            await db.flush()

        access_token = create_access_token(str(user.id))
        refresh_token, token_hash, expires_at = create_refresh_token(str(user.id))

        db.add(
            RefreshToken(
                user_id=user.id,
                token_hash=token_hash,
                expires_at=expires_at,
                is_revoked=False,
            )
        )

        await db.commit()

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
        }

    @staticmethod
    async def login(db: AsyncSession, payload: LoginRequest) -> dict:
        email = normalize_email(str(payload.email))
        if email is None:
            raise HTTPException(status_code=400, detail="Valid email is required")

        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if user is None or not verify_password(payload.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        if not user.is_active:
            raise HTTPException(status_code=403, detail="User account is inactive")

        user.last_login_at = datetime.now(timezone.utc)

        access_token = create_access_token(str(user.id))
        refresh_token, token_hash, expires_at = create_refresh_token(str(user.id))

        db.add(
            RefreshToken(
                user_id=user.id,
                token_hash=token_hash,
                expires_at=expires_at,
                is_revoked=False,
            )
        )

        await db.commit()

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
        }

    @staticmethod
    async def guest_login(db: AsyncSession, payload: GuestLoginRequest) -> dict:
        user = User(
            email=None,
            password_hash=None,
            display_name=payload.display_name,
            role=payload.role,
            is_guest=True,
            is_active=True,
            is_email_verified=False,
        )
        db.add(user)
        await db.flush()

        access_token = create_access_token(str(user.id))
        refresh_token, token_hash, expires_at = create_refresh_token(str(user.id))

        db.add(
            RefreshToken(
                user_id=user.id,
                token_hash=token_hash,
                expires_at=expires_at,
                is_revoked=False,
            )
        )

        await db.commit()

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
        }

    @staticmethod
    async def refresh(db: AsyncSession, payload: RefreshRequest) -> dict:
        try:
            decoded = decode_refresh_token(payload.refresh_token)
        except ValueError:
            raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

        if decoded.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid refresh token type")

        token_hash = hash_token(payload.refresh_token)

        result = await db.execute(
            select(RefreshToken).where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.is_revoked.is_(False),
            )
        )
        stored_token = result.scalar_one_or_none()

        if stored_token is None:
            raise HTTPException(status_code=401, detail="Refresh token not recognized")

        if stored_token.expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=401, detail="Refresh token expired")

        stored_token.is_revoked = True

        user_id = decoded.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid refresh token subject")

        access_token = create_access_token(str(user_id))
        new_refresh_token, new_token_hash, new_expires_at = create_refresh_token(str(user_id))

        db.add(
            RefreshToken(
                user_id=int(user_id),
                token_hash=new_token_hash,
                expires_at=new_expires_at,
                is_revoked=False,
            )
        )

        await db.commit()

        return {
            "access_token": access_token,
            "refresh_token": new_refresh_token,
            "token_type": "bearer",
        }

    @staticmethod
    async def logout(db: AsyncSession, payload: RefreshRequest) -> dict:
        token_hash = hash_token(payload.refresh_token)

        result = await db.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        stored_token = result.scalar_one_or_none()

        if stored_token is not None:
            stored_token.is_revoked = True
            await db.commit()

        return {
            "status": True,
            "message": "Logged out successfully",
        }