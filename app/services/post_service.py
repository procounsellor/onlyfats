from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.models.creator import Creator
from app.models.post import Post
from app.models.post_media import PostMedia
from app.models.creator_subscription import CreatorSubscription


async def get_creator_or_raise(db: AsyncSession, user_id: int):
    result = await db.execute(
        select(Creator).where(
            Creator.user_id == user_id,
            Creator.is_active == True
        )
    )
    creator = result.scalar_one_or_none()
    if not creator:
        raise ValueError("Creator profile not found or inactive")
    return creator


async def create_post(
    db: AsyncSession,
    user_id: int,
    caption: str | None,
    visibility: str,
    media_type: str,
    access_tier: str = "FREE",
):
    creator = await get_creator_or_raise(db, user_id)

    post = Post(
        creator_id=creator.id,
        caption=caption,
        visibility=visibility,
        media_type=media_type,
        access_tier=access_tier,
        status="draft",
        moderation_status="approved"
    )

    db.add(post)
    await db.commit()
    await db.refresh(post)
    return post


async def add_media_to_post(db: AsyncSession, user_id: int, post_id: int, payload):
    creator = await get_creator_or_raise(db, user_id)

    result = await db.execute(
        select(Post).where(
            Post.id == post_id,
            Post.creator_id == creator.id,
            Post.status == "draft"
        )
    )
    post = result.scalar_one_or_none()

    if not post:
        raise ValueError("Draft post not found")

    media = PostMedia(
        post_id=post.id,
        media_kind=payload.media_kind,
        bucket_name=payload.bucket_name,
        object_path=payload.object_path,
        thumbnail_object_path=payload.thumbnail_object_path,
        mime_type=payload.mime_type,
        file_size_bytes=payload.file_size_bytes,
        duration_seconds=payload.duration_seconds,
        width=payload.width,
        height=payload.height,
        sort_order=payload.sort_order,
        processing_status=payload.processing_status
    )

    db.add(media)
    await db.commit()
    await db.refresh(media)
    return media


async def publish_post(db: AsyncSession, user_id: int, post_id: int):
    creator = await get_creator_or_raise(db, user_id)

    result = await db.execute(
        select(Post)
        .options(joinedload(Post.media_items))
        .where(
            Post.id == post_id,
            Post.creator_id == creator.id
        )
    )
    post = result.unique().scalar_one_or_none()

    if not post:
        raise ValueError("Post not found")

    if post.status != "draft":
        raise ValueError("Only draft posts can be published")

    if not post.media_items:
        raise ValueError("Cannot publish post without media")

    post.status = "published"
    post.published_at = datetime.utcnow()

    await db.commit()
    await db.refresh(post)
    return post


async def get_creator_posts(db: AsyncSession, creator_id: int):
    result = await db.execute(
        select(Post)
        .options(joinedload(Post.media_items))
        .where(
            Post.creator_id == creator_id,
            Post.status == "published"
        )
        .order_by(Post.created_at.desc())
    )
    return result.unique().scalars().all()


async def get_single_post(db: AsyncSession, post_id: int):
    result = await db.execute(
        select(Post)
        .options(
            selectinload(Post.media_items),
            selectinload(Post.creator)
        )
        .where(
            Post.id == post_id,
            Post.status == "published"
        )
    )
    return result.scalar_one_or_none()


async def has_active_subscription(db: AsyncSession, viewer_user_id: int, creator_id: int) -> bool:
    result = await db.execute(
        select(CreatorSubscription).where(
            CreatorSubscription.subscriber_user_id == viewer_user_id,
            CreatorSubscription.creator_id == creator_id,
            CreatorSubscription.status == "ACTIVE"
        )
    )
    sub = result.scalar_one_or_none()
    return sub is not None


async def get_my_posts(db: AsyncSession, user_id: int):
    creator = await get_creator_or_raise(db, user_id)
    result = await db.execute(
        select(Post)
        .options(joinedload(Post.media_items))
        .where(
            Post.creator_id == creator.id,
            Post.status.in_(["draft", "published"]),
        )
        .order_by(Post.created_at.desc())
    )
    return result.unique().scalars().all()


async def update_post(db: AsyncSession, user_id: int, post_id: int, payload):
    creator = await get_creator_or_raise(db, user_id)
    result = await db.execute(
        select(Post).where(Post.id == post_id, Post.creator_id == creator.id)
    )
    post = result.scalar_one_or_none()
    if not post:
        raise ValueError("Post not found")
    if payload.caption is not None:
        post.caption = payload.caption
    if payload.visibility is not None:
        post.visibility = payload.visibility
    if payload.access_tier is not None:
        post.access_tier = payload.access_tier
    await db.commit()
    await db.refresh(post)
    return post


async def delete_post(db: AsyncSession, user_id: int, post_id: int):
    creator = await get_creator_or_raise(db, user_id)
    result = await db.execute(
        select(Post).where(Post.id == post_id, Post.creator_id == creator.id)
    )
    post = result.scalar_one_or_none()
    if not post:
        raise ValueError("Post not found")
    post.status = "deleted"
    if creator.post_count and creator.post_count > 0:
        creator.post_count -= 1
    await db.commit()


async def get_feed(db: AsyncSession, viewer_user_id: int, limit: int = 20, creator_id_filter: int | None = None):
    filters = [Post.status == "published", Post.moderation_status == "approved"]
    if creator_id_filter is not None:
        filters.append(Post.creator_id == creator_id_filter)

    result = await db.execute(
        select(Post)
        .options(
            selectinload(Post.media_items),
            selectinload(Post.creator)
        )
        .where(*filters)
        .order_by(Post.created_at.desc())
        .limit(limit)
    )
    posts = result.scalars().all()

    items = []
    for post in posts:
        creator_user_id = post.creator.user_id if post.creator else None
        access = (
            post.visibility == "public"
            or creator_user_id == viewer_user_id
            or await has_active_subscription(db, viewer_user_id, post.creator_id)
        )

        def media_url(m):
            path = m.object_path or ""
            if path.startswith("http"):
                return path
            # GCS object path — frontend will route through /api/v1/media/ proxy
            return path if path else None

        if access:
            media_data = [{"url": media_url(m), "media_kind": m.media_kind, "sort_order": m.sort_order} for m in post.media_items]
        else:
            # locked — only return thumbnail of first item
            media_data = []
            if post.media_items:
                m = post.media_items[0]
                thumb = m.thumbnail_object_path or m.object_path or ""
                url = thumb if thumb.startswith("http") else thumb if thumb else None
                media_data = [{"url": url, "media_kind": m.media_kind, "sort_order": 0}]

        creator = post.creator
        items.append({
            "post_id": post.id,
            "creator_id": post.creator_id,
            "creator_display_name": creator.display_name if creator else None,
            "creator_avatar": creator.profile_image_url if creator else None,
            "creator_handle": f"@{(creator.display_name or 'creator').lower().replace(' ', '')}" if creator else None,
            "caption": post.caption,
            "visibility": post.visibility,
            "media_type": post.media_type,
            "access_tier": post.access_tier,
            "like_count": post.like_count,
            "comment_count": post.comment_count,
            "has_access": access,
            "locked": not access,
            "created_at": post.created_at.isoformat() if post.created_at else None,
            "media": media_data,
        })

    return items