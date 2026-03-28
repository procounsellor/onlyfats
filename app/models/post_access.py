from sqlalchemy import BigInteger, Column, String, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.models.base import Base


class PostAccessLedger(Base):
    __tablename__ = "post_access_ledger"

    id = Column(BigInteger, primary_key=True, autoincrement=True, index=True)

    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    creator_id = Column(BigInteger, ForeignKey("creators.id", ondelete="CASCADE"), nullable=False, index=True)
    post_id = Column(BigInteger, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True)

    access_type = Column(String, nullable=False)  # FREE_ACCESS / SUBSCRIPTION_ACCESS / PREVIEW_ACCESS
    plan_code = Column(String, nullable=True)
    quota_bucket = Column(String, nullable=True)  # EXCLUSIVE_PREVIEW / VIP_PREVIEW

    accessed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
