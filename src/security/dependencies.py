from fastapi import Depends, HTTPException, status, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings, BaseAppSettings
from database import get_db, UserModel
from exceptions import BaseSecurityError
from security.interfaces import JWTAuthManagerInterface
from security.token_manager import JWTAuthManager


def get_jwt_auth_manager(
        settings: BaseAppSettings = Depends(get_settings)
) -> JWTAuthManagerInterface:
    """
    Create and return a JWT authentication manager instance.

    This function uses the provided application settings to instantiate a JWTAuthManager,
    which implements the JWTAuthManagerInterface. The manager is configured with secret
    keys for access and refresh tokens as well as the JWT signing algorithm specified
    in the settings.
    """
    return JWTAuthManager(
        secret_key_access=settings.SECRET_KEY_ACCESS,
        secret_key_refresh=settings.SECRET_KEY_REFRESH,
        algorithm=settings.JWT_SIGNING_ALGORITHM
    )


async def get_user(
        authorization: str = Header(None),
        jwt_manager: JWTAuthManagerInterface = Depends(get_jwt_auth_manager),
        db: AsyncSession = Depends(get_db),
) -> UserModel:
    """
    Dependency to extract and validate the current user from the Authorization header.

    This dependency performs complete JWT-based authentication:
    1. Validates the Authorization header is present
    2. Validates the format is "Bearer <token>"
    3. Decodes the JWT access token
    4. Retrieves the user from the database using the user_id from the token
    5. Verifies the user exists and is active
    """

    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header is missing"
        )

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format. Expected 'Bearer <token>'"
        )

    token = parts[1]

    try:
        payload = jwt_manager.decode_access_token(token)
    except BaseSecurityError as e:
        if "expired" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired."
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token."
            )

    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload."
        )

    stmt = select(UserModel).where(UserModel.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or not active."
        )

    return user
