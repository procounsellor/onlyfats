from sqlalchemy import Column, BigInteger, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.models.base import Base


class Creator(Base):
    __tablename__ = "creators"

    id = Column(BigInteger, primary_key=True, index=True)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)

    display_name = Column(String(150), nullable=True)
    bio = Column(Text, nullable=True)
    profile_image_url = Column(Text, nullable=True)
    header_image_url = Column(Text, nullable=True)
    subscriber_count = Column(BigInteger, nullable=False, default=0)
    post_count = Column(BigInteger, nullable=False, default=0)
    total_likes = Column(BigInteger, nullable=False, default=0)
    location = Column(String(100), nullable=True)
    website_url = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    posts = relationship("Post", back_populates="creator")