"""Likes, comments, bookmarks, follows."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, delete, func
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.like import Like
from app.models.comment import Comment
from app.models.bookmark import Bookmark
from app.models.follow import Follow
from app.models.post import Post
from app.models.creator import Creator
from app.models.notification import Notification

router = APIRouter()


# ── Likes ────────────────────────────────────────────────────────────────────

@router.post("/posts/{post_id}/like")
async def toggle_like(post_id: int, db: AsyncSession = Depends(get_db), current_user=Depends(get_current_user)):
    post = await db.get(Post, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    result = await db.execute(select(Like).where(Like.user_id == current_user.id, Like.post_id == post_id))
    existing = result.scalar_one_or_none()

    if existing:
        await db.delete(existing)
        post.like_count = max(0, (post.like_count or 0) - 1)
        liked = False
    else:
        like = Like(user_id=current_user.id, post_id=post_id)
        db.add(like)
        post.like_count = (post.like_count or 0) + 1
        liked = True

        # notify post creator
        creator_result = await db.execute(select(Creator).where(Creator.id == post.creator_id))
        creator = creator_result.scalar_one_or_none()
        if creator and creator.user_id != current_user.id:
            notif = Notification(
                user_id=creator.user_id,
                actor_id=current_user.id,
                type="new_like",
                title=f"{current_user.display_name} liked your post",
                entity_type="post",
                entity_id=post_id,
            )
            db.add(notif)

    await db.commit()
    return {"liked": liked, "like_count": post.like_count}


@router.get("/posts/{post_id}/liked")
async def is_liked(post_id: int, db: AsyncSession = Depends(get_db), current_user=Depends(get_current_user)):
    result = await db.execute(select(Like).where(Like.user_id == current_user.id, Like.post_id == post_id))
    return {"liked": result.scalar_one_or_none() is not None}


# ── Comments ─────────────────────────────────────────────────────────────────

class AddCommentRequest(BaseModel):
    body: str


@router.get("/posts/{post_id}/comments")
async def list_comments(post_id: int, db: AsyncSession = Depends(get_db), current_user=Depends(get_current_user)):
    result = await db.execute(
        select(Comment)
        .options(joinedload(Comment.user))
        .where(Comment.post_id == post_id, Comment.is_deleted == False)
        .order_by(Comment.created_at.asc())
    )
    comments = result.unique().scalars().all()
    return [
        {
            "id": c.id,
            "user_id": c.user_id,
            "display_name": c.user.display_name if c.user else "Unknown",
            "body": c.body,
            "created_at": c.created_at.isoformat(),
            "is_mine": c.user_id == current_user.id,
        }
        for c in comments
    ]


@router.post("/posts/{post_id}/comments")
async def add_comment(post_id: int, payload: AddCommentRequest, db: AsyncSession = Depends(get_db), current_user=Depends(get_current_user)):
    post = await db.get(Post, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    comment = Comment(post_id=post_id, user_id=current_user.id, body=payload.body.strip())
    db.add(comment)
    post.comment_count = (post.comment_count or 0) + 1

    creator_result = await db.execute(select(Creator).where(Creator.id == post.creator_id))
    creator = creator_result.scalar_one_or_none()
    if creator and creator.user_id != current_user.id:
        notif = Notification(
            user_id=creator.user_id,
            actor_id=current_user.id,
            type="new_comment",
            title=f"{current_user.display_name} commented on your post",
            body=payload.body[:100],
            entity_type="post",
            entity_id=post_id,
        )
        db.add(notif)

    await db.commit()
    await db.refresh(comment)
    return {"id": comment.id, "body": comment.body, "created_at": comment.created_at.isoformat()}


@router.delete("/posts/{post_id}/comments/{comment_id}")
async def delete_comment(post_id: int, comment_id: int, db: AsyncSession = Depends(get_db), current_user=Depends(get_current_user)):
    comment = await db.get(Comment, comment_id)
    if not comment or comment.post_id != post_id:
        raise HTTPException(status_code=404, detail="Comment not found")
    if comment.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your comment")
    comment.is_deleted = True
    post = await db.get(Post, post_id)
    if post:
        post.comment_count = max(0, (post.comment_count or 0) - 1)
    await db.commit()
    return {"status": True}


# ── Bookmarks ────────────────────────────────────────────────────────────────

@router.post("/posts/{post_id}/bookmark")
async def toggle_bookmark(post_id: int, db: AsyncSession = Depends(get_db), current_user=Depends(get_current_user)):
    post = await db.get(Post, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    result = await db.execute(select(Bookmark).where(Bookmark.user_id == current_user.id, Bookmark.post_id == post_id))
    existing = result.scalar_one_or_none()

    if existing:
        await db.delete(existing)
        saved = False
    else:
        bm = Bookmark(user_id=current_user.id, post_id=post_id)
        db.add(bm)
        saved = True

    await db.commit()
    return {"saved": saved}


@router.get("/bookmarks")
async def list_bookmarks(db: AsyncSession = Depends(get_db), current_user=Depends(get_current_user)):
    result = await db.execute(
        select(Bookmark)
        .options(
            joinedload(Bookmark.post).joinedload(Post.media_items),
            joinedload(Bookmark.post).joinedload(Post.creator),
        )
        .where(Bookmark.user_id == current_user.id)
        .order_by(Bookmark.created_at.desc())
    )
    bookmarks = result.unique().scalars().all()
    items = []
    for bm in bookmarks:
        p = bm.post
        if not p:
            continue
        media = p.media_items[0] if p.media_items else None
        items.append({
            "post_id": p.id,
            "caption": p.caption,
            "creator_display_name": p.creator.display_name if p.creator else None,
            "cover_url": media.object_path if media else None,
            "media_type": p.media_type,
            "saved_at": bm.created_at.isoformat(),
        })
    return items


# ── Follows ──────────────────────────────────────────────────────────────────

@router.post("/creators/{creator_id}/follow")
async def toggle_follow(creator_id: int, db: AsyncSession = Depends(get_db), current_user=Depends(get_current_user)):
    creator = await db.get(Creator, creator_id)
    if not creator:
        raise HTTPException(status_code=404, detail="Creator not found")

    result = await db.execute(select(Follow).where(Follow.follower_id == current_user.id, Follow.creator_id == creator_id))
    existing = result.scalar_one_or_none()

    if existing:
        await db.delete(existing)
        following = False
    else:
        follow = Follow(follower_id=current_user.id, creator_id=creator_id)
        db.add(follow)
        following = True

        notif = Notification(
            user_id=creator.user_id,
            actor_id=current_user.id,
            type="new_subscriber",
            title=f"{current_user.display_name} started following you",
            entity_type="creator",
            entity_id=creator_id,
        )
        db.add(notif)

    await db.commit()
    return {"following": following}


@router.get("/creators/{creator_id}/follow")
async def is_following(creator_id: int, db: AsyncSession = Depends(get_db), current_user=Depends(get_current_user)):
    result = await db.execute(select(Follow).where(Follow.follower_id == current_user.id, Follow.creator_id == creator_id))
    return {"following": result.scalar_one_or_none() is not None}
