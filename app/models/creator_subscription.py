# from sqlalchemy import Column, BigInteger, String, Boolean, DateTime, ForeignKey
# from sqlalchemy.sql import func
# from app.models.base import Base


# class CreatorSubscription(Base):
#     __tablename__ = "creator_subscriptions"

#     id = Column(BigInteger, primary_key=True, index=True)
#     subscriber_user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
#     creator_id = Column(BigInteger, ForeignKey("creators.id", ondelete="CASCADE"), nullable=False, index=True)

#     status = Column(String(30), nullable=False)
#     current_period_start = Column(DateTime, nullable=True)
#     current_period_end = Column(DateTime, nullable=True)
#     auto_renew = Column(Boolean, nullable=False, default=False)

#     created_at = Column(DateTime, nullable=False, server_default=func.now())
#     updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

from sqlalchemy import Column, BigInteger, String, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.models.base import Base


class CreatorSubscription(Base):
    __tablename__ = "creator_subscriptions"

    id = Column(BigInteger, primary_key=True, index=True)

    # keep existing working field name so old code does not fail
    subscriber_user_id = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    creator_id = Column(
        BigInteger,
        ForeignKey("creators.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # existing field, keep for backward compatibility
    status = Column(String(30), nullable=False, default="ACTIVE")

    # existing period fields, keep so old code continues to work
    current_period_start = Column(DateTime, nullable=True)
    current_period_end = Column(DateTime, nullable=True)

    auto_renew = Column(Boolean, nullable=False, default=False)

    # nullable=True so existing rows and old code won't fail
    plan_id = Column(
        BigInteger,
        ForeignKey("subscription_plans.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    plan_code = Column(String(30), nullable=True)  # FREE / EXCLUSIVE / VIP

    payment_id = Column(String(255), nullable=True)
    payment_order_id = Column(String(255), nullable=True)

    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now()
    )

    @property
    def user_id(self):
        """
        Backward/forward compatibility helper.
        Newer service code may expect `user_id`,
        while old code still uses `subscriber_user_id`.
        """
        return self.subscriber_user_id

    @property
    def start_at(self):
        """
        Compatibility helper for newer subscription code.
        """
        return self.current_period_start

    @property
    def end_at(self):
        """
        Compatibility helper for newer subscription code.
        """
        return self.current_period_end