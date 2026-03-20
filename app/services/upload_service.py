# import re
# import uuid
# from typing import Optional

# from fastapi import UploadFile
# from google.cloud import storage
# from starlette.concurrency import run_in_threadpool


# def _sanitize_filename(filename: Optional[str]) -> str:
#     if not filename or not filename.strip():
#         return "file"
#     name = filename.strip().replace("\\", "/").split("/")[-1]
#     name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
#     return name[:100] if name else "file"


# def _guess_media_kind(content_type: Optional[str]) -> str:
#     if not content_type:
#         return "file"
#     if content_type.startswith("image/"):
#         return "photo"
#     if content_type.startswith("video/"):
#         return "video"
#     return "file"


# def _build_object_path(
#     *,
#     purpose: str,
#     user_id: int,
#     creator_id: Optional[int],
#     original_filename: str,
# ) -> str:
#     """
#     GCS path layout:

#       user_profile    →  user-profiles/{user_id}/{shard}/{uuid}_{filename}
#       creator_profile →  creator-profiles/{creator_id}/{shard}/{uuid}_{filename}
#       post_media      →  post-media/{creator_id}/{shard}/{uuid}_{filename}

#     All post media is scoped under the creator. The post_id is NOT part of the
#     path — the upload happens before the post is created. The returned object_path
#     is passed into the create/add-media API to link it to a post in the DB.

#     shard = first 2 hex chars of the UUID, distributes keys across GCS's
#     internal metadata index even at millions of objects per creator.
#     """
#     safe_name = _sanitize_filename(original_filename)
#     uid = uuid.uuid4().hex
#     shard = uid[:2]
#     unique_name = f"{uid}_{safe_name}"

#     if purpose == "user_profile":
#         return f"user-profiles/{user_id}/{shard}/{unique_name}"

#     if purpose == "creator_profile":
#         if creator_id is None:
#             raise ValueError("creator_id required for creator_profile upload")
#         return f"creator-profiles/{creator_id}/{shard}/{unique_name}"

#     if purpose == "post_media":
#         if creator_id is None:
#             raise ValueError("creator_id required for post_media upload")
#         return f"post-media/{creator_id}/{shard}/{unique_name}"

#     raise ValueError(f"Invalid purpose: {purpose!r}")


# def _upload_bytes_sync(
#     *,
#     bucket_name: str,
#     object_path: str,
#     file_bytes: bytes,
#     content_type: Optional[str],
# ) -> None:
#     client = storage.Client()
#     bucket = client.bucket(bucket_name)
#     blob = bucket.blob(object_path)
#     blob.upload_from_string(file_bytes, content_type=content_type)


# async def upload_file_to_gcs(
#     *,
#     bucket_name: str,
#     purpose: str,
#     user_id: int,
#     creator_id: Optional[int] = None,
#     file: UploadFile,
# ) -> dict:
#     file_bytes = await file.read()
#     if not file_bytes:
#         raise ValueError(f"File '{file.filename}' is empty")

#     object_path = _build_object_path(
#         purpose=purpose,
#         user_id=user_id,
#         creator_id=creator_id,
#         original_filename=file.filename or "file",
#     )

#     await run_in_threadpool(
#         _upload_bytes_sync,
#         bucket_name=bucket_name,
#         object_path=object_path,
#         file_bytes=file_bytes,
#         content_type=file.content_type,
#     )

#     return {
#         "object_path": object_path,
#         "storage_uri": f"gs://{bucket_name}/{object_path}",
#         "file_name": file.filename,
#         "mime_type": file.content_type,
#         "media_kind": _guess_media_kind(file.content_type),
#         "file_size_bytes": len(file_bytes),
#     }

import io
import mimetypes
import os
import uuid
from typing import Optional, Tuple

from fastapi import UploadFile
from google.cloud import storage
from PIL import Image

PHOTO_MIME_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
VIDEO_MIME_TYPES = {"video/mp4", "video/quicktime", "video/x-msvideo", "video/webm"}

MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024


def _safe_filename(filename: str) -> str:
    if not filename:
        return "file"
    return os.path.basename(filename).replace(" ", "_")


def _detect_media_kind(mime_type: str) -> str:
    if mime_type in PHOTO_MIME_TYPES:
        return "photo"
    if mime_type in VIDEO_MIME_TYPES:
        return "video"
    raise ValueError(f"Unsupported file type: {mime_type}")


def _extract_image_metadata(file_bytes: bytes) -> Tuple[Optional[int], Optional[int]]:
    try:
        image = Image.open(io.BytesIO(file_bytes))
        return image.size
    except Exception:
        return None, None


def _extract_video_metadata(file_bytes: bytes) -> Tuple[Optional[int], Optional[int], Optional[float]]:
    return None, None, None


def _build_object_path(
    purpose: str,
    user_id: int,
    creator_id: Optional[int],
    file_name: str,
) -> str:
    unique_name = f"{uuid.uuid4().hex}_{file_name}"
    shard = unique_name[:2]

    if purpose == "user_profile":
        return f"user-profiles/{user_id}/{shard}/{unique_name}"

    if purpose == "creator_profile":
        if creator_id is None:
            raise ValueError("creator_id is required for creator_profile")
        return f"creator-profiles/{creator_id}/{shard}/{unique_name}"

    if purpose == "post_media":
        if creator_id is None:
            raise ValueError("creator_id is required for post_media")
        return f"post-media/temp/{creator_id}/{shard}/{unique_name}"

    raise ValueError(f"Unsupported purpose: {purpose}")


async def upload_file_to_gcs(
    bucket_name: str,
    purpose: str,
    user_id: int,
    creator_id: Optional[int],
    file: UploadFile,
) -> dict:
    if file is None or not file.filename:
        raise ValueError("Invalid file")

    file_name = _safe_filename(file.filename)

    content = await file.read()
    if not content:
        raise ValueError(f"Uploaded file is empty: {file_name}")

    file_size_bytes = len(content)
    if file_size_bytes > MAX_FILE_SIZE_BYTES:
        raise ValueError(f"File too large: {file_name}")

    mime_type = file.content_type or mimetypes.guess_type(file_name)[0]
    if not mime_type:
        raise ValueError(f"Could not determine MIME type for file: {file_name}")

    media_kind = _detect_media_kind(mime_type)

    width: Optional[int] = None
    height: Optional[int] = None
    duration_seconds: Optional[float] = None
    thumbnail_object_path: Optional[str] = None

    if media_kind == "photo":
        width, height = _extract_image_metadata(content)
        processing_status = "ready"
    else:
        width, height, duration_seconds = _extract_video_metadata(content)
        processing_status = "uploaded"

    object_path = _build_object_path(
        purpose=purpose,
        user_id=user_id,
        creator_id=creator_id,
        file_name=file_name,
    )

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(object_path)

    blob.upload_from_string(content, content_type=mime_type)

    return {
        "bucket_name": bucket_name,
        "object_path": object_path,
        "storage_uri": f"gs://{bucket_name}/{object_path}",
        "file_name": file_name,
        "mime_type": mime_type,
        "media_kind": media_kind,
        "file_size_bytes": file_size_bytes,
        "width": width,
        "height": height,
        "duration_seconds": duration_seconds,
        "thumbnail_object_path": thumbnail_object_path,
        "processing_status": processing_status,
    }