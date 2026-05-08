import uuid
from datetime import datetime

import oss2
from fastapi import APIRouter, UploadFile, File, HTTPException

from app.configs.settings import settings

router = APIRouter(tags=["upload"])

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/svg+xml", "image/webp", "image/x-icon", "image/gif"}
MAX_FILE_SIZE = 2 * 1024 * 1024  # 2 MB


def _get_bucket() -> oss2.Bucket:
    auth = oss2.Auth(settings.OSS_ACCESS_KEY, settings.OSS_SECRET_KEY)
    return oss2.Bucket(auth, settings.OSS_URL, settings.OSS_BUCKET)


@router.post("/upload/image")
async def upload_image(file: UploadFile = File(...)):
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail=f"不支持的图片格式: {file.content_type}")

    data = await file.read()
    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="文件大小不能超过 2MB")

    ext = _ext_from_content_type(file.content_type)
    date_prefix = datetime.now().strftime("%Y/%m/%d")
    object_key = f"uploads/{date_prefix}/{uuid.uuid4().hex}{ext}"

    bucket = _get_bucket()
    bucket.put_object(object_key, data, headers={"Content-Type": file.content_type})

    url = f"{settings.OSS_ADDR}/{object_key}"
    return {"url": url}


def _ext_from_content_type(ct: str) -> str:
    mapping = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/svg+xml": ".svg",
        "image/webp": ".webp",
        "image/x-icon": ".ico",
        "image/gif": ".gif",
    }
    return mapping.get(ct, ".bin")
