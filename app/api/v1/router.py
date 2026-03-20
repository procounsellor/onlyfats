from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1 import creator_posts
from app.api.v1 import creator_profile
from app.api.v1 import uploads

api_router = APIRouter()
api_router.include_router(auth_router)

api_router.include_router(
    creator_profile.router,
    prefix="/creators",
    tags=["Creator Profile"]
)

api_router.include_router(
    creator_posts.router,
    prefix="",
    tags=["Creator Posts"]
)

api_router.include_router(
    uploads.router,
    prefix="",
    tags=["Uploads"]
)