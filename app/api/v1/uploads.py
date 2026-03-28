from typing import List

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.security import decode_access_token
from app.models.creator import Creator
from app.models.user import User
from app.services.upload_service import upload_file_to_gcs

router = APIRouter()

VALID_PURPOSES = {"user_profile", "creator_profile", "post_media"}


@router.post("/uploads")
async def upload_files(
    purpose: str = Form(..., description="user_profile | creator_profile | post_media"),
    files: List[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if purpose not in VALID_PURPOSES:
        raise HTTPException(status_code=400, detail=f"Invalid purpose. Must be one of: {', '.join(sorted(VALID_PURPOSES))}")

    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    creator_id = None
    if purpose in {"creator_profile", "post_media"}:
        result = await db.execute(
            select(Creator).where(Creator.user_id == current_user.id, Creator.is_active == True)
        )
        creator = result.scalar_one_or_none()
        if not creator:
            raise HTTPException(status_code=404, detail="Creator profile not found")
        creator_id = creator.id

    uploaded = []
    for file in files:
        if not file or not file.filename:
            continue
        try:
            item = await upload_file_to_gcs(
                bucket_name=settings.GCS_BUCKET_NAME,
                purpose=purpose,
                user_id=current_user.id,
                creator_id=creator_id,
                file=file,
            )
            uploaded.append(item)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Upload failed for {file.filename}: {str(e)}")

    if not uploaded:
        raise HTTPException(status_code=400, detail="No valid files were uploaded")

    return {"status": True, "message": "Files uploaded successfully", "data": uploaded}


@router.get("/media/{object_path:path}")
async def serve_media(
    request: Request,
    object_path: str,
    token: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Stream a private GCS object. Accepts token via Authorization header or ?token= query param."""
    # Resolve token from header or query param
    raw_token = token
    if not raw_token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            raw_token = auth_header[7:]

    if not raw_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        payload = decode_access_token(raw_token)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    subject = payload.get("sub")
    if not subject or payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token payload")

    result = await db.execute(select(User).where(User.id == int(subject), User.is_active.is_(True)))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=401, detail="User not found")

    try:
        from google.cloud import storage
        from fastapi.responses import StreamingResponse
        import io
        client = storage.Client()
        bucket = client.bucket(settings.GCS_BUCKET_NAME)
        blob = bucket.blob(object_path)
        data = blob.download_as_bytes()
        content_type = blob.content_type or "application/octet-stream"
        return StreamingResponse(io.BytesIO(data), media_type=content_type)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Media not found: {str(e)}")
