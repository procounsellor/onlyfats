from sqlalchemy import BigInteger, Column, String, Integer, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.models.base import Base


class SubscriptionUsage(Base):
    __tablename__ = "subscription_usages"

    id = Column(BigInteger, primary_key=True, autoincrement=True, index=True)

    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    creator_id = Column(BigInteger, ForeignKey("creators.id", ondelete="CASCADE"), nullable=False, index=True)

    plan_code = Column(String, nullable=False)
    usage_type = Column(String, nullable=False)  # EXCLUSIVE_PREVIEW / VIP_PREVIEW

    used_count = Column(Integer, nullable=False, default=0)
    allowed_count = Column(Integer, nullable=False, default=0)

    cycle_key = Column(String, nullable=False, index=True)  # e.g. 2026-03
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
