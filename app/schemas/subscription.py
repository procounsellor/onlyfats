from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class SubscriptionPlanCreate(BaseModel):
    code: str
    name: str
    description: Optional[str] = None
    price_in_paise: int = 0
    duration_days: int = 30
    currency: str = "INR"
    active: bool = True
    unlimited_free_content: bool = True
    unlimited_exclusive_content: bool = False
    unlimited_vip_content: bool = False
    exclusive_preview_quota: int = 0
    vip_preview_quota: int = 0


class SubscriptionPlanResponse(BaseModel):
    id: str
    creator_id: str
    code: str
    name: str
    description: Optional[str] = None
    price_in_paise: int
    duration_days: int
    currency: str
    active: bool
    unlimited_free_content: bool
    unlimited_exclusive_content: bool
    unlimited_vip_content: bool
    exclusive_preview_quota: int
    vip_preview_quota: int

    class Config:
        from_attributes = True


class BulkSubscriptionPlanUpsertRequest(BaseModel):
    plans: List[SubscriptionPlanCreate]


class SubscribeRequest(BaseModel):
    plan_code: str


class SubscriptionResponse(BaseModel):
    id: str
    user_id: str
    creator_id: str
    plan_id: str
    plan_code: str
    status: str
    start_at: datetime
    end_at: datetime
    auto_renew: bool

    class Config:
        from_attributes = True


class RemainingEntitlements(BaseModel):
    exclusive_preview_remaining: int = 0
    vip_preview_remaining: int = 0


class MyCreatorSubscriptionResponse(BaseModel):
    subscription: Optional[SubscriptionResponse] = None
    entitlements: RemainingEntitlements


class PostAccessResponse(BaseModel):
    can_access: bool
    access_reason: str
    required_plan: Optional[str] = None
    quota_consumed: bool = False
    remaining_preview_count: int = 0
    already_unlocked: bool = False