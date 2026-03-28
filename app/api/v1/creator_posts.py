from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.database import get_db
from app.models.creator import Creator
from app.schemas.post import CreatePostRequest, AddPostMediaRequest, UpdatePostRequest
from app.services.post_service import (
    create_post,
    add_media_to_post,
    publish_post,
    get_creator_posts,
    get_single_post,
    get_feed,
    has_active_subscription,
    get_my_posts,
    update_post,
    delete_post,
)

router = APIRouter(tags=["Creator Posts"])


@router.get("/creator/posts/me")
async def get_my_creator_posts(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    try:
        posts = await get_my_posts(db, current_user.id)
        return {
            "status": True,
            "count": len(posts),
            "data": [
                {
                    "post_id": p.id,
                    "creator_id": p.creator_id,
                    "caption": p.caption,
                    "visibility": p.visibility,
                    "media_type": p.media_type,
                    "access_tier": p.access_tier,
                    "status": p.status,
                    "like_count": p.like_count,
                    "comment_count": p.comment_count,
                    "published_at": p.published_at.isoformat() if p.published_at else None,
                    "created_at": p.created_at.isoformat() if p.created_at else None,
                    "media": [
                        {
                            "id": m.id,
                            "media_kind": m.media_kind,
                            "object_path": m.object_path,
                            "thumbnail_object_path": m.thumbnail_object_path,
                            "sort_order": m.sort_order,
                        }
                        for m in sorted(p.media_items, key=lambda x: x.sort_order)
                    ],
                }
                for p in posts
            ],
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/creator/posts/{post_id}")
async def update_creator_post(
    post_id: int,
    request: UpdatePostRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    try:
        post = await update_post(db, current_user.id, post_id, request)
        return {
            "status": True,
            "message": "Post updated",
            "data": {
                "post_id": post.id,
                "caption": post.caption,
                "visibility": post.visibility,
                "access_tier": post.access_tier,
                "status": post.status,
            },
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/creator/posts/{post_id}")
async def delete_creator_post(
    post_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    try:
        await delete_post(db, current_user.id, post_id)
        return {"status": True, "message": "Post deleted"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/creator/posts")
async def create_creator_post(
    request: CreatePostRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    try:
        post = await create_post(
            db,
            current_user.id,
            request.caption,
            request.visibility,
            request.media_type,
            request.access_tier,
        )
        return {
            "status": True,
            "message": "Draft post created successfully",
            "data": {
                "post_id": post.id,
                "status": post.status
            }
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/creator/posts/{post_id}/media")
async def add_post_media_api(
    post_id: int,
    request: AddPostMediaRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    try:
        media = await add_media_to_post(db, current_user.id, post_id, request)
        return {
            "status": True,
            "message": "Media added successfully",
            "data": {
                "media_id": media.id,
                "post_id": media.post_id,
                "media_kind": media.media_kind,
                "bucket_name": media.bucket_name,
                "object_path": media.object_path,
                "thumbnail_object_path": media.thumbnail_object_path,
                "processing_status": media.processing_status
            }
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/creator/posts/{post_id}/publish")
async def publish_creator_post(
    post_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    try:
        post = await publish_post(db, current_user.id, post_id)
        return {
            "status": True,
            "message": "Post published successfully",
            "data": {
                "post_id": post.id,
                "status": post.status,
                "published_at": post.published_at.isoformat() if post.published_at else None
            }
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/creators/{creator_id}/posts")
async def get_posts_of_creator(
    creator_id: int,
    db: AsyncSession = Depends(get_db)
):
    posts = await get_creator_posts(db, creator_id)
    return {
        "status": True,
        "count": len(posts),
        "data": [
            {
                "post_id": p.id,
                "creator_id": p.creator_id,
                "caption": p.caption,
                "visibility": p.visibility,
                "media_type": p.media_type,
                "status": p.status,
                "published_at": p.published_at.isoformat() if p.published_at else None,
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "media": [
                    {
                        "id": m.id,
                        "media_kind": m.media_kind,
                        "bucket_name": m.bucket_name,
                        "object_path": m.object_path,
                        "thumbnail_object_path": m.thumbnail_object_path,
                        "mime_type": m.mime_type,
                        "file_size_bytes": m.file_size_bytes,
                        "duration_seconds": m.duration_seconds,
                        "width": m.width,
                        "height": m.height,
                        "sort_order": m.sort_order,
                        "processing_status": m.processing_status
                    }
                    for m in p.media_items
                ]
            }
            for p in posts
        ]
    }


@router.get("/posts/feed")
async def get_posts_feed(
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    creator_id_filter = None
    if current_user.role == "creator":
        result = await db.execute(
            select(Creator).where(Creator.user_id == current_user.id, Creator.is_active == True)
        )
        creator = result.scalar_one_or_none()
        if creator:
            creator_id_filter = creator.id

    items = await get_feed(db, current_user.id, limit, creator_id_filter=creator_id_filter)
    return items


@router.get("/posts/{post_id}")
async def get_post_details(
    post_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    post = await get_single_post(db, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    is_owner = post.creator is not None and post.creator.user_id == current_user.id
    has_access = (
        post.visibility == "public"
        or is_owner
        or await has_active_subscription(db, current_user.id, post.creator_id)
    )

    if not has_access:
        media = [
            {
                "id": m.id,
                "media_kind": m.media_kind,
                "thumbnail_object_path": m.thumbnail_object_path,
                "processing_status": m.processing_status
            }
            for m in post.media_items
        ]
    else:
        media = [
            {
                "id": m.id,
                "media_kind": m.media_kind,
                "bucket_name": m.bucket_name,
                "object_path": m.object_path,
                "thumbnail_object_path": m.thumbnail_object_path,
                "mime_type": m.mime_type,
                "file_size_bytes": m.file_size_bytes,
                "duration_seconds": m.duration_seconds,
                "width": m.width,
                "height": m.height,
                "sort_order": m.sort_order,
                "processing_status": m.processing_status
            }
            for m in post.media_items
        ]

    return {
        "status": True,
        "data": {
            "post_id": post.id,
            "creator_id": post.creator_id,
            "caption": post.caption,
            "visibility": post.visibility,
            "media_type": post.media_type,
            "status": post.status,
            "like_count": post.like_count,
            "comment_count": post.comment_count,
            "has_access": has_access,
            "locked": not has_access,
            "media": media
        }
    }