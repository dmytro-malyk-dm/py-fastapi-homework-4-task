from datetime import date

from fastapi import (
    APIRouter,
    Depends,
    status,
    HTTPException,
    UploadFile,
    Form,
    File
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_s3_storage_client
from database import get_db, UserModel, UserProfileModel, UserGroupEnum
from exceptions import S3FileUploadError
from schemas.profiles import ProfileResponseSchema
from security.dependencies import get_user
from storages import S3StorageInterface
from validation import (
    validate_name,
    validate_image,
    validate_gender,
    validate_birth_date
)

router = APIRouter()


def _validate_profile_input(
    first_name: str,
    last_name: str,
    gender: str,
    date_of_birth: date,
    info: str,
    avatar: UploadFile
) -> None:
    """Validate all profile input fields."""
    try:
        validate_name(first_name)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    try:
        validate_name(last_name)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    if not info or not info.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Info cannot be empty or consist only of spaces."
        )

    try:
        validate_gender(gender)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    try:
        validate_birth_date(date_of_birth)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    try:
        validate_image(avatar)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


def _check_authorization(
    current_user: UserModel,
    user_id: int
) -> None:
    """Check if user has permission to create profile."""
    is_admin = current_user.has_group(UserGroupEnum.ADMIN)
    if not is_admin and current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to edit this profile."
        )


async def _verify_target_user(
    user_id: int,
    db: AsyncSession
) -> None:
    """Verify target user exists and is active."""
    stmt = select(UserModel).where(UserModel.id == user_id)
    result = await db.execute(stmt)
    target_user = result.scalar_one_or_none()

    if not target_user or not target_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or not active."
        )


async def _check_existing_profile(
    user_id: int,
    db: AsyncSession
) -> None:
    """Check if profile already exists."""
    stmt = select(UserProfileModel).where(
        UserProfileModel.user_id == user_id
    )
    result = await db.execute(stmt)
    existing_profile = result.scalar_one_or_none()

    if existing_profile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User already has a profile."
        )


async def _upload_avatar(
    user_id: int,
    avatar: UploadFile,
    s3_client: S3StorageInterface
) -> str:
    """Upload avatar to S3 and return key."""
    avatar_key = f"avatars/{user_id}_avatar.jpg"

    try:
        avatar.file.seek(0)
        avatar_content = avatar.file.read()
        await s3_client.upload_file(avatar_key, avatar_content)
    except S3FileUploadError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload avatar. Please try again later."
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload avatar. Please try again later."
        )

    return avatar_key


async def _create_profile_in_db(
    user_id: int,
    first_name: str,
    last_name: str,
    gender: str,
    date_of_birth: date,
    info: str,
    avatar_key: str,
    db: AsyncSession
) -> UserProfileModel:
    """Create profile in database."""
    new_profile = UserProfileModel(
        user_id=user_id,
        first_name=first_name.lower(),
        last_name=last_name.lower(),
        gender=gender,
        date_of_birth=date_of_birth,
        info=info,
        avatar=avatar_key
    )

    db.add(new_profile)

    try:
        await db.commit()
        await db.refresh(new_profile)
    except Exception:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create profile. Please try again later."
        )

    return new_profile


@router.post(
    "/users/{user_id}/profile/",
    response_model=ProfileResponseSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Create user profile",
    description="Create a user profile with avatar upload to S3 storage",
)
async def create_user_profile(
    user_id: int,
    first_name: str = Form(...),
    last_name: str = Form(...),
    gender: str = Form(...),
    date_of_birth: date = Form(...),
    info: str = Form(...),
    avatar: UploadFile = File(...),
    current_user: UserModel = Depends(get_user),
    db: AsyncSession = Depends(get_db),
    s3_client: S3StorageInterface = Depends(get_s3_storage_client),
) -> ProfileResponseSchema:
    """
    Create a user profile with validation and avatar upload.

    Authorization Rules:
    - A user can only create their own profile
    - Admins can create profiles for any user
    """
    _validate_profile_input(
        first_name, last_name, gender, date_of_birth, info, avatar
    )

    _check_authorization(current_user, user_id)

    await _verify_target_user(user_id, db)

    await _check_existing_profile(user_id, db)

    avatar_key = await _upload_avatar(user_id, avatar, s3_client)

    new_profile = await _create_profile_in_db(
        user_id, first_name, last_name, gender,
        date_of_birth, info, avatar_key, db
    )

    avatar_url = await s3_client.get_file_url(avatar_key)

    return ProfileResponseSchema(
        id=new_profile.id,
        user_id=new_profile.user_id,
        first_name=new_profile.first_name,
        last_name=new_profile.last_name,
        gender=new_profile.gender,
        date_of_birth=new_profile.date_of_birth,
        info=new_profile.info,
        avatar=avatar_url
    )
