from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr


class MeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr | None
    display_name: str
    role: str
    is_guest: bool
    is_active: bool
    is_email_verified: bool
    profile_image_url: Optional[str] = None