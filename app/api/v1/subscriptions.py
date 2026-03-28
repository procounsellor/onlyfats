from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.schemas.subscription import (
    BulkSubscriptionPlanUpsertRequest,
    SubscribeRequest,
)
from app.services.subscription_service import SubscriptionService
from app.models.creator_subscription import CreatorSubscription
from app.models.creator import Creator
from app.models.subscription import SubscriptionPlan
from app.models.subscription_usage import SubscriptionUsage

router = APIRouter(tags=["Subscriptions"])


@router.get("/creators/{creator_id}/subscription-plans")
async def get_creator_subscription_plans(creator_id: int, db: AsyncSession = Depends(get_db)):
    service = SubscriptionService(db)
    plans = await service.get_creator_plans(creator_id)
    return [
        {
            "id": p.id,
            "code": p.code,
            "name": p.name,
            "description": p.description,
            "price_in_paise": p.price_in_paise,
            "duration_days": p.duration_days,
            "currency": p.currency,
        }
        for p in plans
    ]


@router.post("/creators/me/subscription-plans")
async def upsert_my_subscription_plans(
    request: BulkSubscriptionPlanUpsertRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Creator).where(Creator.user_id == current_user.id, Creator.is_active == True)
    )
    creator = result.scalar_one_or_none()
    if not creator:
        raise HTTPException(status_code=400, detail="Creator profile not found")
    service = SubscriptionService(db)
    try:
        plans = await service.upsert_creator_plans(creator.id, request.plans)
        return {"status": True, "message": "Plans upserted successfully", "data": plans}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/creators/{creator_id}/subscriptions")
async def subscribe_to_creator(
    creator_id: int,
    request: SubscribeRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = SubscriptionService(db)
    try:
        await service.subscribe_to_creator(current_user.id, creator_id, request.plan_code)
        return {"status": True, "message": "Subscribed successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/creators/{creator_id}/subscriptions/me")
async def get_my_creator_subscription(
    creator_id: int,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = SubscriptionService(db)
    data = await service.get_my_subscription(current_user.id, creator_id)
    return {"status": True, "data": data}


@router.get("/posts/{post_id}/access")
async def check_post_access(
    post_id: int,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = SubscriptionService(db)
    try:
        data = await service.check_post_access(current_user.id, post_id)
        return {"status": True, "data": data}
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/posts/{post_id}/unlock")
async def unlock_post(
    post_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = SubscriptionService(db)
    try:
        data = await service.unlock_post(current_user.id, post_id)
        return {"status": True, "message": "Post unlocked evaluation complete", "data": data}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/subscriptions/me")
async def get_my_subscriptions(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return all active subscriptions for the current user with creator + quota info."""
    now = datetime.utcnow()
    subs_result = await db.execute(
        select(CreatorSubscription).where(
            CreatorSubscription.subscriber_user_id == current_user.id,
            CreatorSubscription.status == "ACTIVE",
            CreatorSubscription.current_period_end >= now,
        ).order_by(CreatorSubscription.created_at.desc())
    )
    subs = subs_result.scalars().all()

    from datetime import datetime as dt
    cycle_key = f"{now.year}-{now.month:02d}"

    items = []
    for sub in subs:
        creator_result = await db.execute(select(Creator).where(Creator.id == sub.creator_id))
        creator = creator_result.scalar_one_or_none()
        if not creator:
            continue

        plan_result = await db.execute(
            select(SubscriptionPlan).where(
                SubscriptionPlan.creator_id == sub.creator_id,
                SubscriptionPlan.code == sub.plan_code,
            )
        )
        plan = plan_result.scalar_one_or_none()

        # Quota remaining
        excl_remaining = None
        vip_remaining = None
        if sub.plan_code == "FREE" and plan:
            usage_result = await db.execute(
                select(SubscriptionUsage).where(
                    SubscriptionUsage.user_id == current_user.id,
                    SubscriptionUsage.creator_id == sub.creator_id,
                    SubscriptionUsage.usage_type == "EXCLUSIVE_PREVIEW",
                    SubscriptionUsage.cycle_key == cycle_key,
                )
            )
            usage = usage_result.scalar_one_or_none()
            if usage:
                excl_remaining = max(usage.allowed_count - usage.used_count, 0)
            else:
                excl_remaining = plan.exclusive_preview_quota if plan else 0

        if sub.plan_code == "EXCLUSIVE" and plan:
            usage_result = await db.execute(
                select(SubscriptionUsage).where(
                    SubscriptionUsage.user_id == current_user.id,
                    SubscriptionUsage.creator_id == sub.creator_id,
                    SubscriptionUsage.usage_type == "VIP_PREVIEW",
                    SubscriptionUsage.cycle_key == cycle_key,
                )
            )
            usage = usage_result.scalar_one_or_none()
            if usage:
                vip_remaining = max(usage.allowed_count - usage.used_count, 0)
            else:
                vip_remaining = plan.vip_preview_quota if plan else 0

        items.append({
            "subscription_id": sub.id,
            "creator_id": creator.id,
            "creator_display_name": creator.display_name,
            "creator_profile_image_url": creator.profile_image_url,
            "creator_header_image_url": creator.header_image_url,
            "creator_bio": creator.bio,
            "creator_subscriber_count": creator.subscriber_count,
            "creator_post_count": creator.post_count,
            "plan_code": sub.plan_code,
            "plan_name": plan.name if plan else sub.plan_code,
            "plan_price_in_paise": plan.price_in_paise if plan else 0,
            "status": sub.status,
            "current_period_end": sub.current_period_end.isoformat() if sub.current_period_end else None,
            "auto_renew": sub.auto_renew,
            "exclusive_preview_remaining": excl_remaining,
            "vip_preview_remaining": vip_remaining,
            "perks": _plan_perks(sub.plan_code, plan),
        })

    return items


from pydantic import BaseModel as _PBM

class ChangePlanRequest(_PBM):
    plan_code: str


@router.post("/subscriptions/{subscription_id}/cancel")
async def cancel_subscription(
    subscription_id: int,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CreatorSubscription).where(
            CreatorSubscription.id == subscription_id,
            CreatorSubscription.subscriber_user_id == current_user.id,
            CreatorSubscription.status == "ACTIVE",
        )
    )
    sub = result.scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")

    sub.status = "CANCELLED"
    sub.auto_renew = False

    # Decrement creator subscriber count
    creator_result = await db.execute(select(Creator).where(Creator.id == sub.creator_id))
    creator = creator_result.scalar_one_or_none()
    if creator and creator.subscriber_count > 0:
        creator.subscriber_count -= 1

    await db.commit()
    return {"status": True, "message": "Subscription cancelled"}


@router.post("/subscriptions/{subscription_id}/change-plan")
async def change_subscription_plan(
    subscription_id: int,
    payload: ChangePlanRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if payload.plan_code not in ("FREE", "EXCLUSIVE", "VIP"):
        raise HTTPException(status_code=400, detail="Invalid plan code")

    result = await db.execute(
        select(CreatorSubscription).where(
            CreatorSubscription.id == subscription_id,
            CreatorSubscription.subscriber_user_id == current_user.id,
            CreatorSubscription.status == "ACTIVE",
        )
    )
    sub = result.scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")

    if sub.plan_code == payload.plan_code:
        raise HTTPException(status_code=400, detail="Already on this plan")

    # Verify the plan exists for this creator
    plan_result = await db.execute(
        select(SubscriptionPlan).where(
            SubscriptionPlan.creator_id == sub.creator_id,
            SubscriptionPlan.code == payload.plan_code,
            SubscriptionPlan.active == True,
        )
    )
    if not plan_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Plan not available for this creator")

    sub.plan_code = payload.plan_code
    await db.commit()
    return {"status": True, "message": f"Plan changed to {payload.plan_code}"}


def _plan_perks(plan_code: str, plan) -> list:
    if plan_code == "FREE":
        quota = plan.exclusive_preview_quota if plan else 1
        return [
            "Unlimited FREE posts",
            f"{quota} EXCLUSIVE post preview/month",
            "No VIP access",
        ]
    if plan_code == "EXCLUSIVE":
        quota = plan.vip_preview_quota if plan else 3
        return [
            "Unlimited FREE posts",
            "Unlimited EXCLUSIVE posts",
            f"{quota} VIP post previews/month",
        ]
    if plan_code == "VIP":
        return [
            "Unlimited FREE posts",
            "Unlimited EXCLUSIVE posts",
            "Unlimited VIP posts",
        ]
    return []
