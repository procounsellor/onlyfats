# from sqlalchemy import Column, BigInteger, String, Text, DateTime, ForeignKey
# from sqlalchemy.sql import func
# from sqlalchemy.orm import relationship
# from app.models.base import Base


# class Post(Base):
#     __tablename__ = "posts"

#     id = Column(BigInteger, primary_key=True, index=True)
#     creator_id = Column(BigInteger, ForeignKey("creators.id", ondelete="CASCADE"), nullable=False, index=True)

#     caption = Column(Text, nullable=True)
#     visibility = Column(String(20), nullable=False, default="public")  # public, subscribers_only
#     media_type = Column(String(20), nullable=False)  # image, video, mixed

#     status = Column(String(20), nullable=False, default="draft")  # draft, published, archived, deleted
#     moderation_status = Column(String(20), nullable=False, default="approved")

#     like_count = Column(BigInteger, nullable=False, default=0)
#     comment_count = Column(BigInteger, nullable=False, default=0)

#     published_at = Column(DateTime, nullable=True)
#     deleted_at = Column(DateTime, nullable=True)

#     created_at = Column(DateTime, nullable=False, server_default=func.now())
#     updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

#     creator = relationship("Creator", back_populates="posts")
#     media_items = relationship("PostMedia", back_populates="post", cascade="all, delete-orphan")

from sqlalchemy import Column, BigInteger, String, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.models.base import Base


class Post(Base):
    __tablename__ = "posts"

    id = Column(BigInteger, primary_key=True, index=True)
    creator_id = Column(
        BigInteger,
        ForeignKey("creators.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    caption = Column(Text, nullable=True)

    # existing fields - keep as-is so old code keeps working
    visibility = Column(String(20), nullable=False, default="public")  # public, subscribers_only
    media_type = Column(String(20), nullable=False)  # image, video, mixed

    status = Column(String(20), nullable=False, default="draft")  # draft, published, archived, deleted
    moderation_status = Column(String(20), nullable=False, default="approved")

    like_count = Column(BigInteger, nullable=False, default=0)
    comment_count = Column(BigInteger, nullable=False, default=0)

    # NEW: subscription tier for gated content
    # keep nullable=False with default so existing code and old rows behave safely
    access_tier = Column(String(20), nullable=False, default="FREE")  # FREE, EXCLUSIVE, VIP

    published_at = Column(DateTime, nullable=True)
    deleted_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now()
    )

    creator = relationship("Creator", back_populates="posts")
    media_items = relationship("PostMedia", back_populates="post", cascade="all, delete-orphan")

    @property
    def is_published(self):
        """
        Compatibility helper for newer code that expects boolean publish status.
        Old system uses status='published'.
        """
        return self.status == "published"