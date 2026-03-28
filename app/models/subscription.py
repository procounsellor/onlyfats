from sqlalchemy import BigInteger, Column, String, Integer, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.models.base import Base


class SubscriptionPlan(Base):
    __tablename__ = "subscription_plans"

    id = Column(BigInteger, primary_key=True, autoincrement=True, index=True)
    creator_id = Column(BigInteger, ForeignKey("creators.id", ondelete="CASCADE"), nullable=False, index=True)

    code = Column(String, nullable=False)  # FREE / EXCLUSIVE / VIP
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)

    price_in_paise = Column(Integer, nullable=False, default=0)
    duration_days = Column(Integer, nullable=False, default=30)
    currency = Column(String, nullable=False, default="INR")

    active = Column(Boolean, nullable=False, default=True)

    unlimited_free_content = Column(Boolean, nullable=False, default=True)
    unlimited_exclusive_content = Column(Boolean, nullable=False, default=False)
    unlimited_vip_content = Column(Boolean, nullable=False, default=False)

    exclusive_preview_quota = Column(Integer, nullable=False, default=0)
    vip_preview_quota = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)