from datetime import date

from fastapi import UploadFile, Form, File
from pydantic import BaseModel, field_validator, HttpUrl

from validation import (
    validate_name,
    validate_image,
    validate_gender,
    validate_birth_date
)


class ProfileCreateSchema(BaseModel):
    """Schema for creating a user profile with form data and file upload."""

    first_name: str
    last_name: str
    gender: str
    date_of_birth: date
    info: str
    avatar: UploadFile

    @field_validator("first_name")
    @classmethod
    def validate_first_name(cls, v: str) -> str:
        """Validate that first name contains only English letters."""
        validate_name(v)
        return v.lower()

    @field_validator("last_name")
    @classmethod
    def validate_last_name(cls, v: str) -> str:
        """Validate that last name contains only English letters."""
        validate_name(v)
        return v.lower()

    @field_validator("info")
    @classmethod
    def validate_info(cls, v: str) -> str:
        """Validate that info is not empty or whitespace only."""
        if not v or not v.strip():
            raise ValueError("Info cannot be empty or consist only of spaces.")
        return v

    @field_validator("gender")
    @classmethod
    def validate_gender_field(cls, v: str) -> str:
        """Validate that gender is a valid option."""
        validate_gender(v)
        return v

    @field_validator("date_of_birth")
    @classmethod
    def validate_date_of_birth_field(cls, v: date) -> date:
        """Validate that date of birth meets age requirements."""
        validate_birth_date(v)
        return v

    @field_validator("avatar")
    @classmethod
    def validate_avatar_field(cls, v: UploadFile) -> UploadFile:
        """Validate that avatar is a valid image file."""
        validate_image(v)
        return v


class ProfileResponseSchema(BaseModel):
    """Schema for profile response."""

    id: int
    user_id: int
    first_name: str
    last_name: str
    gender: str
    date_of_birth: date
    info: str
    avatar: str

    model_config = {
        "from_attributes": True
    }
