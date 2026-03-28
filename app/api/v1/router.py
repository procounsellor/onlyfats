from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1 import creator_posts
from app.api.v1 import creator_profile
from app.api.v1 import uploads
from app.api.v1 import subscriptions
from app.api.v1 import messages
from app.api.v1 import notifications
from app.api.v1 import social
from app.api.v1 import users

api_router = APIRouter()

api_router.include_router(auth_router)

api_router.include_router(creator_profile.router, prefix="/creators", tags=["Creator Profile"])
api_router.include_router(creator_posts.router, prefix="", tags=["Creator Posts"])
api_router.include_router(uploads.router, prefix="", tags=["Uploads"])
api_router.include_router(subscriptions.router, prefix="", tags=["Subscriptions"])
api_router.include_router(messages.router, prefix="", tags=["Messages"])
api_router.include_router(notifications.router, prefix="", tags=["Notifications"])
api_router.include_router(social.router, prefix="", tags=["Social"])
api_router.include_router(users.router, prefix="", tags=["Users"])
