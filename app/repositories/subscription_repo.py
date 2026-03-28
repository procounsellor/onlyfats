from datetime import datetime
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.subscription import SubscriptionPlan
from app.models.creator_subscription import CreatorSubscription
from app.models.subscription_usage import SubscriptionUsage
from app.models.post_access import PostAccessLedger


class SubscriptionRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ---------- plans ----------
    async def get_creator_plans(self, creator_id: str):
        result = await self.db.execute(
            select(SubscriptionPlan)
            .where(
                SubscriptionPlan.creator_id == creator_id,
                SubscriptionPlan.active == True,
            )
            .order_by(SubscriptionPlan.price_in_paise.asc())
        )
        return result.scalars().all()

    async def get_plan_by_code(self, creator_id: str, code: str):
        result = await self.db.execute(
            select(SubscriptionPlan).where(
                SubscriptionPlan.creator_id == creator_id,
                SubscriptionPlan.code == code,
                SubscriptionPlan.active == True,
            )
        )
        return result.scalar_one_or_none()

    async def upsert_plan(self, creator_id: str, payload: dict):
        result = await self.db.execute(
            select(SubscriptionPlan).where(
                SubscriptionPlan.creator_id == creator_id,
                SubscriptionPlan.code == payload["code"],
            )
        )
        plan = result.scalar_one_or_none()

        if plan:
            for key, value in payload.items():
                setattr(plan, key, value)
        else:
            plan = SubscriptionPlan(creator_id=creator_id, **payload)
            self.db.add(plan)

        await self.db.commit()
        await self.db.refresh(plan)
        return plan

    # ---------- subscriptions ----------
    async def get_active_subscription(self, user_id: str, creator_id: str):
        now = datetime.utcnow()
        result = await self.db.execute(
            select(CreatorSubscription)
            .where(
                CreatorSubscription.subscriber_user_id == user_id,
                CreatorSubscription.creator_id == creator_id,
                CreatorSubscription.status == "ACTIVE",
                CreatorSubscription.current_period_start <= now,
                CreatorSubscription.current_period_end >= now,
            )
            .order_by(CreatorSubscription.created_at.desc())
        )
        return result.scalar_one_or_none()

    async def expire_active_subscriptions(self, user_id: str, creator_id: str):
        now = datetime.utcnow()
        result = await self.db.execute(
            select(CreatorSubscription).where(
                CreatorSubscription.subscriber_user_id == user_id,
                CreatorSubscription.creator_id == creator_id,
                CreatorSubscription.status == "ACTIVE",
            )
        )
        subs = result.scalars().all()
        for sub in subs:
            sub.status = "EXPIRED"
            sub.current_period_end = now
        await self.db.commit()

    async def create_subscription(self, data: dict):
        sub = CreatorSubscription(**data)
        self.db.add(sub)
        await self.db.commit()
        await self.db.refresh(sub)
        return sub

    # ---------- usage ----------
    async def get_usage(self, user_id: str, creator_id: str, usage_type: str, cycle_key: str):
        result = await self.db.execute(
            select(SubscriptionUsage).where(
                SubscriptionUsage.user_id == user_id,
                SubscriptionUsage.creator_id == creator_id,
                SubscriptionUsage.usage_type == usage_type,
                SubscriptionUsage.cycle_key == cycle_key,
            )
        )
        return result.scalar_one_or_none()

    async def create_or_update_usage(
        self,
        user_id: str,
        creator_id: str,
        plan_code: str,
        usage_type: str,
        allowed_count: int,
        cycle_key: str,
        increment: bool = False,
    ):
        usage = await self.get_usage(user_id, creator_id, usage_type, cycle_key)

        if usage:
            usage.allowed_count = allowed_count
            usage.plan_code = plan_code
            if increment:
                usage.used_count += 1
        else:
            usage = SubscriptionUsage(
                user_id=user_id,
                creator_id=creator_id,
                plan_code=plan_code,
                usage_type=usage_type,
                allowed_count=allowed_count,
                used_count=1 if increment else 0,
                cycle_key=cycle_key,
            )
            self.db.add(usage)

        await self.db.commit()
        await self.db.refresh(usage)
        return usage

    # ---------- access ledger ----------
    async def has_post_already_unlocked(self, user_id: str, post_id: str):
        result = await self.db.execute(
            select(PostAccessLedger).where(
                PostAccessLedger.user_id == user_id,
                PostAccessLedger.post_id == post_id,
            )
        )
        return result.scalar_one_or_none() is not None

    async def create_post_access(self, data: dict):
        access = PostAccessLedger(**data)
        self.db.add(access)
        await self.db.commit()
        await self.db.refresh(access)
        return access
