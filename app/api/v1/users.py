"""User + creator public profile APIs."""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.security import hash_password, verify_password
from app.models.user import User
from app.models.creator import Creator
from app.models.post import Post
from app.models.follow import Follow
from app.models.creator_subscription import CreatorSubscription
from app.models.subscription_usage import SubscriptionUsage

router = APIRouter()


class UpdateProfileRequest(BaseModel):
    display_name: Optional[str] = None
    bio: Optional[str] = None
    profile_image_url: Optional[str] = None
    header_image_url: Optional[str] = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.get("/users/me")
async def get_my_profile(db: AsyncSession = Depends(get_db), current_user=Depends(get_current_user)):
    from sqlalchemy import func
    from app.models.creator_subscription import CreatorSubscription as CS

    creator = None
    creator_stats = {}
    if current_user.role == "creator":
        result = await db.execute(select(Creator).where(Creator.user_id == current_user.id))
        creator = result.scalar_one_or_none()

        if creator:
            post_count = (await db.execute(
                select(func.count()).select_from(Post).where(Post.creator_id == creator.id, Post.status == "published")
            )).scalar() or 0

            subscriber_count = (await db.execute(
                select(func.count()).select_from(CS).where(CS.creator_id == creator.id, CS.status == "ACTIVE")
            )).scalar() or 0

            total_likes = (await db.execute(
                select(func.coalesce(func.sum(Post.like_count), 0)).where(Post.creator_id == creator.id, Post.status == "published")
            )).scalar() or 0

            free_count = (await db.execute(
                select(func.count()).select_from(Post).where(Post.creator_id == creator.id, Post.status == "published", Post.access_tier == "FREE")
            )).scalar() or 0

            exclusive_count = (await db.execute(
                select(func.count()).select_from(Post).where(Post.creator_id == creator.id, Post.status == "published", Post.access_tier == "EXCLUSIVE")
            )).scalar() or 0

            vip_count = (await db.execute(
                select(func.count()).select_from(Post).where(Post.creator_id == creator.id, Post.status == "published", Post.access_tier == "VIP")
            )).scalar() or 0

            creator_stats = {
                "post_count": post_count,
                "subscriber_count": subscriber_count,
                "total_likes": total_likes,
                "free_count": free_count,
                "exclusive_count": exclusive_count,
                "vip_count": vip_count,
            }

    # Count active subscriptions (for visitors)
    sub_count_result = await db.execute(
        select(func.count()).select_from(CS).where(
            CS.subscriber_user_id == current_user.id,
            CS.status == "ACTIVE",
        )
    )
    sub_count = sub_count_result.scalar() or 0

    return {
        "id": current_user.id,
        "email": current_user.email,
        "display_name": current_user.display_name,
        "role": current_user.role,
        "is_guest": current_user.is_guest,
        "bio": current_user.bio,
        "profile_image_url": current_user.profile_image_url,
        "subscription_count": sub_count,
        "creator": {
            "id": creator.id,
            "display_name": creator.display_name,
            "bio": creator.bio,
            "profile_image_url": creator.profile_image_url,
            "header_image_url": creator.header_image_url,
            "location": creator.location,
            "website_url": creator.website_url,
            **creator_stats,
        } if creator else None,
    }


@router.put("/users/me")
async def update_my_profile(payload: UpdateProfileRequest, db: AsyncSession = Depends(get_db), current_user=Depends(get_current_user)):
    # Always update on the User row itself
    if payload.display_name:
        current_user.display_name = payload.display_name
    if payload.bio is not None:
        current_user.bio = payload.bio
    if payload.profile_image_url is not None:
        current_user.profile_image_url = payload.profile_image_url

    # Also mirror to Creator record if this user is a creator
    if current_user.role == "creator":
        result = await db.execute(select(Creator).where(Creator.user_id == current_user.id))
        creator = result.scalar_one_or_none()
        if creator:
            if payload.display_name:
                creator.display_name = payload.display_name
            if payload.bio is not None:
                creator.bio = payload.bio
            if payload.profile_image_url is not None:
                creator.profile_image_url = payload.profile_image_url
            if payload.header_image_url is not None:
                creator.header_image_url = payload.header_image_url

    await db.commit()
    return {"status": True, "message": "Profile updated"}


@router.post("/users/change-password")
async def change_password(payload: ChangePasswordRequest, db: AsyncSession = Depends(get_db), current_user=Depends(get_current_user)):
    if current_user.is_guest:
        raise HTTPException(status_code=400, detail="Guest accounts cannot change password")
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    current_user.password_hash = hash_password(payload.new_password)
    await db.commit()
    return {"status": True}


@router.get("/creators/{creator_id}/profile")
async def get_creator_profile(creator_id: int, db: AsyncSession = Depends(get_db), current_user=Depends(get_current_user)):
    result = await db.execute(
        select(Creator)
        .options(joinedload(Creator.posts).joinedload(Post.media_items))
        .where(Creator.id == creator_id, Creator.is_active == True)
    )
    creator = result.unique().scalar_one_or_none()
    if not creator:
        raise HTTPException(status_code=404, detail="Creator not found")

    now = datetime.utcnow()
    sub_result = await db.execute(
        select(CreatorSubscription).where(
            CreatorSubscription.subscriber_user_id == current_user.id,
            CreatorSubscription.creator_id == creator_id,
            CreatorSubscription.status == "ACTIVE",
            CreatorSubscription.current_period_end >= now,
        )
    )
    subscription = sub_result.scalar_one_or_none()
    plan_code = subscription.plan_code if subscription else None
    is_owner = creator.user_id == current_user.id

    follow_result = await db.execute(
        select(Follow).where(Follow.follower_id == current_user.id, Follow.creator_id == creator_id)
    )
    is_following_val = follow_result.scalar_one_or_none() is not None

    # Quota remaining for this viewer
    cycle_key = f"{now.year}-{now.month:02d}"
    excl_remaining = None
    vip_remaining = None

    if plan_code == "FREE":
        u = await db.execute(
            select(SubscriptionUsage).where(
                SubscriptionUsage.user_id == current_user.id,
                SubscriptionUsage.creator_id == creator_id,
                SubscriptionUsage.usage_type == "EXCLUSIVE_PREVIEW",
                SubscriptionUsage.cycle_key == cycle_key,
            )
        )
        row = u.scalar_one_or_none()
        excl_remaining = max(row.allowed_count - row.used_count, 0) if row else 1

    if plan_code == "EXCLUSIVE":
        u = await db.execute(
            select(SubscriptionUsage).where(
                SubscriptionUsage.user_id == current_user.id,
                SubscriptionUsage.creator_id == creator_id,
                SubscriptionUsage.usage_type == "VIP_PREVIEW",
                SubscriptionUsage.cycle_key == cycle_key,
            )
        )
        row = u.scalar_one_or_none()
        vip_remaining = max(row.allowed_count - row.used_count, 0) if row else 3

    def _post_access(post):
        """Determine access state for a single post given the viewer's tier."""
        tier = post.access_tier  # FREE / EXCLUSIVE / VIP
        if is_owner:
            return True, None          # creator sees own content
        if tier == "FREE":
            return True, None          # FREE posts always visible
        if plan_code == "VIP":
            return True, None          # VIP sees everything
        if plan_code == "EXCLUSIVE":
            if tier == "EXCLUSIVE":
                return True, None
            if tier == "VIP":
                # Locked — but show quota
                return False, "VIP"
        if plan_code == "FREE":
            if tier == "EXCLUSIVE":
                return False, "EXCLUSIVE"   # quota tracked separately
            if tier == "VIP":
                return False, "VIP"
        # no subscription
        return False, tier

    published_posts = [p for p in creator.posts if p.status == "published"]
    posts_data = []
    for p in sorted(published_posts, key=lambda x: x.created_at or 0, reverse=True):
        can_access, required_tier = _post_access(p)
        media = p.media_items[0] if p.media_items else None
        posts_data.append({
            "post_id": p.id,
            "caption": p.caption,
            "media_type": p.media_type,
            "access_tier": p.access_tier,
            "cover_url": media.object_path if media else None,
            "locked": not can_access,
            "required_tier": required_tier,
            "like_count": p.like_count,
            "comment_count": p.comment_count,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        })

    return {
        "id": creator.id,
        "display_name": creator.display_name,
        "bio": creator.bio,
        "profile_image_url": creator.profile_image_url,
        "header_image_url": creator.header_image_url,
        "subscriber_count": creator.subscriber_count,
        "post_count": len(published_posts),
        "total_likes": creator.total_likes,
        "location": creator.location,
        "website_url": creator.website_url,
        "is_subscribed": subscription is not None,
        "subscription_plan": plan_code,
        "exclusive_preview_remaining": excl_remaining,
        "vip_preview_remaining": vip_remaining,
        "is_following": is_following_val,
        "is_own_profile": is_owner,
        "posts": posts_data,
    }


@router.get("/search/creators")
async def search_creators(q: str = "", db: AsyncSession = Depends(get_db), current_user=Depends(get_current_user)):
    from sqlalchemy import func
    query = select(Creator).where(Creator.is_active == True)
    if q:
        query = query.where(Creator.display_name.ilike(f"%{q}%"))
    query = query.order_by(Creator.subscriber_count.desc()).limit(30)
    result = await db.execute(query)
    creators = result.scalars().all()

    # Compute live post counts for all returned creators in one query
    creator_ids = [c.id for c in creators]
    counts_result = await db.execute(
        select(Post.creator_id, func.count().label("cnt"))
        .where(Post.creator_id.in_(creator_ids), Post.status == "published")
        .group_by(Post.creator_id)
    )
    post_counts = {row.creator_id: row.cnt for row in counts_result}

    return [
        {
            "id": c.id,
            "display_name": c.display_name,
            "bio": c.bio,
            "profile_image_url": c.profile_image_url,
            "subscriber_count": c.subscriber_count,
            "post_count": post_counts.get(c.id, 0),
        }
        for c in creators
    ]
