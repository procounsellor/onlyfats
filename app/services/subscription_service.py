from datetime import datetime, timedelta
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.subscription_repo import SubscriptionRepository
from app.repositories.post_repo import PostRepository
from app.utils.enums import (
    SubscriptionPlanCode,
    PostVisibilityTier,
    UsageType,
)


class SubscriptionService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = SubscriptionRepository(db)
        self.post_repo = PostRepository(db)

    def _cycle_key(self):
        now = datetime.utcnow()
        return f"{now.year}-{now.month:02d}"

    async def get_creator_plans(self, creator_id: str):
        return await self.repo.get_creator_plans(creator_id)

    async def upsert_creator_plans(self, creator_id: str, plans: list):
        results = []
        for plan in plans:
            payload = plan.model_dump()
            results.append(await self.repo.upsert_plan(creator_id, payload))
        return results

    async def subscribe_to_creator(self, user_id: str, creator_id: str, plan_code: str):
        plan = await self.repo.get_plan_by_code(creator_id, plan_code)
        if not plan:
            raise ValueError("Subscription plan not found")

        await self.repo.expire_active_subscriptions(user_id, creator_id)

        now = datetime.utcnow()
        end_at = now + timedelta(days=plan.duration_days)

        sub = await self.repo.create_subscription({
            "subscriber_user_id": user_id,
            "creator_id": creator_id,
            "plan_id": plan.id,
            "plan_code": plan.code,
            "status": "ACTIVE",
            "current_period_start": now,
            "current_period_end": end_at,
            "auto_renew": False,
            "payment_id": None,
            "payment_order_id": None,
        })

        cycle_key = self._cycle_key()

        if plan.code == SubscriptionPlanCode.FREE.value:
            await self.repo.create_or_update_usage(
                user_id=user_id,
                creator_id=creator_id,
                plan_code=plan.code,
                usage_type=UsageType.EXCLUSIVE_PREVIEW.value,
                allowed_count=plan.exclusive_preview_quota,
                cycle_key=cycle_key,
                increment=False,
            )
            await self.repo.create_or_update_usage(
                user_id=user_id,
                creator_id=creator_id,
                plan_code=plan.code,
                usage_type=UsageType.VIP_PREVIEW.value,
                allowed_count=plan.vip_preview_quota,
                cycle_key=cycle_key,
                increment=False,
            )

        elif plan.code == SubscriptionPlanCode.EXCLUSIVE.value:
            await self.repo.create_or_update_usage(
                user_id=user_id,
                creator_id=creator_id,
                plan_code=plan.code,
                usage_type=UsageType.VIP_PREVIEW.value,
                allowed_count=plan.vip_preview_quota,
                cycle_key=cycle_key,
                increment=False,
            )

        return sub

    async def get_my_subscription(self, user_id: str, creator_id: str):
        subscription = await self.repo.get_active_subscription(user_id, creator_id)

        cycle_key = self._cycle_key()
        ex_usage = await self.repo.get_usage(
            user_id, creator_id, UsageType.EXCLUSIVE_PREVIEW.value, cycle_key
        )
        vip_usage = await self.repo.get_usage(
            user_id, creator_id, UsageType.VIP_PREVIEW.value, cycle_key
        )

        exclusive_remaining = 0
        vip_remaining = 0

        if ex_usage:
            exclusive_remaining = max(ex_usage.allowed_count - ex_usage.used_count, 0)
        if vip_usage:
            vip_remaining = max(vip_usage.allowed_count - vip_usage.used_count, 0)

        return {
            "subscription": subscription,
            "entitlements": {
                "exclusive_preview_remaining": exclusive_remaining,
                "vip_preview_remaining": vip_remaining,
            }
        }

    async def check_post_access(self, user_id: str, post_id: str):
        post = await self.post_repo.get_post_by_id(post_id)
        if not post:
            raise ValueError("Post not found")

        if not post.is_published:
            return {
                "can_access": False,
                "access_reason": "POST_NOT_PUBLISHED",
                "required_plan": None,
                "quota_consumed": False,
                "remaining_preview_count": 0,
                "already_unlocked": False,
            }

        if post.access_tier == PostVisibilityTier.FREE.value:
            return {
                "can_access": True,
                "access_reason": "FREE_POST",
                "required_plan": None,
                "quota_consumed": False,
                "remaining_preview_count": 0,
                "already_unlocked": False,
            }

        active_sub = await self.repo.get_active_subscription(user_id, post.creator_id)
        already_unlocked = await self.repo.has_post_already_unlocked(user_id, post.id)

        if already_unlocked:
            return {
                "can_access": True,
                "access_reason": "ALREADY_UNLOCKED",
                "required_plan": None,
                "quota_consumed": False,
                "remaining_preview_count": 0,
                "already_unlocked": True,
            }

        cycle_key = self._cycle_key()

        # VIP subscriber
        if active_sub and active_sub.plan_code == SubscriptionPlanCode.VIP.value:
            return {
                "can_access": True,
                "access_reason": "VIP_SUBSCRIBER",
                "required_plan": None,
                "quota_consumed": False,
                "remaining_preview_count": 0,
                "already_unlocked": False,
            }

        # EXCLUSIVE subscriber
        if active_sub and active_sub.plan_code == SubscriptionPlanCode.EXCLUSIVE.value:
            if post.access_tier == PostVisibilityTier.EXCLUSIVE.value:
                return {
                    "can_access": True,
                    "access_reason": "EXCLUSIVE_SUBSCRIBER",
                    "required_plan": None,
                    "quota_consumed": False,
                    "remaining_preview_count": 0,
                    "already_unlocked": False,
                }

            if post.access_tier == PostVisibilityTier.VIP.value:
                usage = await self.repo.get_usage(
                    user_id, post.creator_id, UsageType.VIP_PREVIEW.value, cycle_key
                )
                remaining = 0
                if usage:
                    remaining = max(usage.allowed_count - usage.used_count, 0)

                if remaining > 0:
                    return {
                        "can_access": True,
                        "access_reason": "VIP_PREVIEW_ALLOWED",
                        "required_plan": SubscriptionPlanCode.VIP.value,
                        "quota_consumed": False,
                        "remaining_preview_count": remaining,
                        "already_unlocked": False,
                    }

                return {
                    "can_access": False,
                    "access_reason": "VIP_SUBSCRIPTION_REQUIRED",
                    "required_plan": SubscriptionPlanCode.VIP.value,
                    "quota_consumed": False,
                    "remaining_preview_count": 0,
                    "already_unlocked": False,
                }

        # FREE subscriber or no active subscription
        if post.access_tier == PostVisibilityTier.EXCLUSIVE.value:
            usage = await self.repo.get_usage(
                user_id, post.creator_id, UsageType.EXCLUSIVE_PREVIEW.value, cycle_key
            )
            remaining = 0
            if usage:
                remaining = max(usage.allowed_count - usage.used_count, 0)

            if remaining > 0:
                return {
                    "can_access": True,
                    "access_reason": "EXCLUSIVE_PREVIEW_ALLOWED",
                    "required_plan": SubscriptionPlanCode.EXCLUSIVE.value,
                    "quota_consumed": False,
                    "remaining_preview_count": remaining,
                    "already_unlocked": False,
                }

            return {
                "can_access": False,
                "access_reason": "EXCLUSIVE_SUBSCRIPTION_REQUIRED",
                "required_plan": SubscriptionPlanCode.EXCLUSIVE.value,
                "quota_consumed": False,
                "remaining_preview_count": 0,
                "already_unlocked": False,
            }

        if post.access_tier == PostVisibilityTier.VIP.value:
            return {
                "can_access": False,
                "access_reason": "VIP_SUBSCRIPTION_REQUIRED",
                "required_plan": SubscriptionPlanCode.VIP.value,
                "quota_consumed": False,
                "remaining_preview_count": 0,
                "already_unlocked": False,
            }

        return {
            "can_access": False,
            "access_reason": "ACCESS_DENIED",
            "required_plan": None,
            "quota_consumed": False,
            "remaining_preview_count": 0,
            "already_unlocked": False,
        }

    async def unlock_post(self, user_id: str, post_id: str):
        decision = await self.check_post_access(user_id, post_id)
        if not decision["can_access"]:
            return decision

        post = await self.post_repo.get_post_by_id(post_id)

        if decision["already_unlocked"]:
            return decision

        cycle_key = self._cycle_key()
        access_type = "SUBSCRIPTION_ACCESS"
        quota_bucket = None
        plan_code = None
        quota_consumed = False

        if decision["access_reason"] == "FREE_POST":
            access_type = "FREE_ACCESS"

        elif decision["access_reason"] == "EXCLUSIVE_PREVIEW_ALLOWED":
            usage = await self.repo.get_usage(
                user_id, post.creator_id, UsageType.EXCLUSIVE_PREVIEW.value, cycle_key
            )
            if not usage or usage.used_count >= usage.allowed_count:
                raise ValueError("No exclusive preview quota remaining")

            await self.repo.create_or_update_usage(
                user_id=user_id,
                creator_id=post.creator_id,
                plan_code=usage.plan_code,
                usage_type=UsageType.EXCLUSIVE_PREVIEW.value,
                allowed_count=usage.allowed_count,
                cycle_key=cycle_key,
                increment=True,
            )
            access_type = "PREVIEW_ACCESS"
            quota_bucket = UsageType.EXCLUSIVE_PREVIEW.value
            plan_code = usage.plan_code
            quota_consumed = True

        elif decision["access_reason"] == "VIP_PREVIEW_ALLOWED":
            usage = await self.repo.get_usage(
                user_id, post.creator_id, UsageType.VIP_PREVIEW.value, cycle_key
            )
            if not usage or usage.used_count >= usage.allowed_count:
                raise ValueError("No VIP preview quota remaining")

            await self.repo.create_or_update_usage(
                user_id=user_id,
                creator_id=post.creator_id,
                plan_code=usage.plan_code,
                usage_type=UsageType.VIP_PREVIEW.value,
                allowed_count=usage.allowed_count,
                cycle_key=cycle_key,
                increment=True,
            )
            access_type = "PREVIEW_ACCESS"
            quota_bucket = UsageType.VIP_PREVIEW.value
            plan_code = usage.plan_code
            quota_consumed = True

        await self.repo.create_post_access({
            "user_id": user_id,
            "creator_id": post.creator_id,
            "post_id": post.id,
            "access_type": access_type,
            "plan_code": plan_code,
            "quota_bucket": quota_bucket,
        })

        updated = await self.check_post_access(user_id, post_id)
        updated["quota_consumed"] = quota_consumed
        return updated
