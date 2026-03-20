from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.creator import Creator
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
        raise HTTPException(
            status_code=400,
            detail=f"Invalid purpose. Must be one of: {', '.join(sorted(VALID_PURPOSES))}",
        )

    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    creator_id: Optional[int] = None

    if purpose in {"creator_profile", "post_media"}:
        result = await db.execute(
            select(Creator).where(
                Creator.user_id == current_user.id,
                Creator.is_active == True,
            )
        )
        creator = result.scalar_one_or_none()

        if creator is None or creator.id is None:
            raise HTTPException(status_code=404, detail="Creator profile not found")

        creator_id = creator.id

    uploaded = []

    for file in files:
        if file is None or not file.filename:
            continue

        try:
            item = await upload_file_to_gcs(
                bucket_name=settings.GCS_BUCKET_NAME,
                purpose=purpose,
                user_id=current_user.id,
                creator_id=creator_id,
                file=file,
            )
            if item is not None:
                uploaded.append(item)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Upload failed for {file.filename}: {str(e)}"
            )

    if not uploaded:
        raise HTTPException(status_code=400, detail="No valid files were uploaded")

    return {
        "status": True,
        "message": "Files uploaded successfully",
        "data": uploaded,
    }