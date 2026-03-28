from enum import Enum


class UserRole(str, Enum):
    GUEST = "GUEST"
    USER = "USER"
    CREATOR = "CREATOR"
    ADMIN = "ADMIN"


class PostVisibilityTier(str, Enum):
    FREE = "FREE"
    EXCLUSIVE = "EXCLUSIVE"
    VIP = "VIP"


class SubscriptionPlanCode(str, Enum):
    FREE = "FREE"
    EXCLUSIVE = "EXCLUSIVE"
    VIP = "VIP"


class SubscriptionStatus(str, Enum):
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    PENDING = "PENDING"
    FAILED = "FAILED"


class UsageType(str, Enum):
    EXCLUSIVE_PREVIEW = "EXCLUSIVE_PREVIEW"
    VIP_PREVIEW = "VIP_PREVIEW"