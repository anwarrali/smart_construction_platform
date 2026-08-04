import re
import uuid
from pathlib import Path
from fastapi import HTTPException, UploadFile
from app.core.config import settings
from urllib.parse import urlparse

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
SIGNATURE_VERIFIED_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".webp", ".wav", ".ogg", ".m4a", ".mp3", ".dwg", ".ifc",
}

UPLOAD_RULES = {
    "attachments": {
        ".jpg": {"image/jpeg"}, ".jpeg": {"image/jpeg"}, ".png": {"image/png"},
        ".pdf": {"application/pdf"}, ".doc": {"application/msword"},
        ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/zip"},
        ".xls": {"application/vnd.ms-excel"},
        ".xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "application/zip"},
    },
    "documents": {
        ".jpg": {"image/jpeg"}, ".jpeg": {"image/jpeg"}, ".png": {"image/png"},
        ".pdf": {"application/pdf"}, ".doc": {"application/msword"},
        ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/zip"},
        ".xls": {"application/vnd.ms-excel"},
        ".xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "application/zip"},
        ".txt": {"text/plain"},
        ".dwg": {"application/acad", "application/dwg", "image/vnd.dwg", "application/octet-stream"},
    },
    "site-reports": {
        ".jpg": {"image/jpeg"}, ".jpeg": {"image/jpeg"}, ".png": {"image/png"},
        ".pdf": {"application/pdf"},
    },
    "field-evidence": {
        ".jpg": {"image/jpeg"}, ".jpeg": {"image/jpeg"}, ".png": {"image/png"},
        ".webp": {"image/webp"},
    },
    "avatars": {
        ".jpg": {"image/jpeg"}, ".jpeg": {"image/jpeg"}, ".png": {"image/png"},
        ".webp": {"image/webp"},
    },
    "audio": {
        ".mp3": {"audio/mpeg"}, ".wav": {"audio/wav", "audio/x-wav"},
        ".m4a": {"audio/mp4", "audio/x-m4a"}, ".ogg": {"audio/ogg"},
        ".mp4": {"audio/mp4", "video/mp4"}, ".webm": {"audio/webm", "video/webm"},
        ".mpeg": {"audio/mpeg"}, ".mpga": {"audio/mpeg"},
    },
    "ifc": {
        ".ifc": {"application/x-step", "application/step", "text/plain", "application/octet-stream"},
    },
}


def _matches_signature(extension: str, content: bytes) -> bool:
    if extension in {".jpg", ".jpeg"}:
        return content.startswith(b"\xff\xd8\xff")
    if extension == ".png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if extension == ".pdf":
        return content.startswith(b"%PDF-")
    if extension in {".docx", ".xlsx"}:
        return content.startswith(b"PK\x03\x04")
    if extension in {".doc", ".xls"}:
        return content.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
    if extension == ".webp":
        return content.startswith(b"RIFF") and content[8:12] == b"WEBP"
    if extension == ".wav":
        return content.startswith(b"RIFF") and content[8:12] == b"WAVE"
    if extension == ".ogg":
        return content.startswith(b"OggS")
    if extension == ".m4a":
        return len(content) >= 12 and content[4:8] == b"ftyp"
    if extension == ".mp4":
        return len(content) >= 12 and content[4:8] == b"ftyp"
    if extension == ".webm":
        return content.startswith(b"\x1a\x45\xdf\xa3")
    if extension in {".mpeg", ".mpga"}:
        return content.startswith(b"ID3") or (len(content) >= 2 and content[0] == 0xFF and content[1] & 0xE0 == 0xE0)
    if extension == ".mp3":
        return content.startswith(b"ID3") or (len(content) >= 2 and content[0] == 0xFF and content[1] & 0xE0 == 0xE0)
    if extension == ".dwg":
        return content.startswith(b"AC10")
    if extension == ".ifc":
        sample = content[:65536].lstrip(b"\xef\xbb\xbf\x00\t\r\n ").upper()
        return sample.startswith(b"ISO-10303-21;") and b"HEADER;" in sample and b"DATA;" in sample
    return extension == ".txt"

async def save_upload(file: UploadFile, category: str) -> tuple[str, int]:
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", Path(file.filename or "file").name)
    extension = Path(safe_name).suffix.lower()
    rules = UPLOAD_RULES.get(category)
    mime_type = (file.content_type or "").split(";", 1)[0].strip().lower()
    mime_is_allowed = (
        rules is not None
        and extension in rules
        and (
            mime_type in rules[extension]
            or (mime_type == "application/octet-stream" and extension in SIGNATURE_VERIFIED_EXTENSIONS)
        )
    )
    if not mime_is_allowed:
        raise HTTPException(status_code=415, detail=f"Unsupported file type for {category}")
    first_chunk = await file.read(1024 * 1024)
    if not first_chunk:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if not _matches_signature(extension, first_chunk):
        raise HTTPException(status_code=415, detail="File content does not match its extension")
    relative = Path(category) / f"{uuid.uuid4()}_{safe_name}"
    target = Path(settings.UPLOAD_DIR).resolve() / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    try:
        with target.open("wb") as output:
            chunk = first_chunk
            while chunk:
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="File exceeds the 25 MB limit")
                output.write(chunk)
                chunk = await file.read(1024 * 1024)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return f"{settings.BACKEND_URL.rstrip('/')}/uploads/{relative.as_posix()}", size


async def save_private_upload(file: UploadFile, category: str) -> tuple[str, int]:
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", Path(file.filename or "file").name)
    extension = Path(safe_name).suffix.lower()
    rules = UPLOAD_RULES.get(category)
    mime_type = (file.content_type or "").split(";", 1)[0].strip().lower()
    allowed = (
        rules is not None
        and extension in rules
        and (
            mime_type in rules[extension]
            or (mime_type == "application/octet-stream" and extension in SIGNATURE_VERIFIED_EXTENSIONS)
        )
    )
    if not allowed:
        raise HTTPException(status_code=415, detail=f"Unsupported file type for {category}")
    first_chunk = await file.read(1024 * 1024)
    if not first_chunk:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if not _matches_signature(extension, first_chunk):
        raise HTTPException(status_code=415, detail="File content does not match its extension")
    storage_key = (Path(category) / f"{uuid.uuid4()}_{safe_name}").as_posix()
    target = resolve_private_storage_key(storage_key)
    target.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    try:
        with target.open("wb") as output:
            chunk = first_chunk
            while chunk:
                size += len(chunk)
                limit = settings.IFC_MAX_FILE_MB * 1024 * 1024 if category == "ifc" else MAX_UPLOAD_BYTES
                if size > limit:
                    raise HTTPException(status_code=413, detail=f"File exceeds the {limit // (1024 * 1024)} MB limit")
                output.write(chunk)
                chunk = await file.read(1024 * 1024)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return storage_key, size

def delete_upload(file_url: str | None) -> None:
    if not file_url:
        return
    marker = "/uploads/"
    path = urlparse(file_url).path
    if marker not in path:
        return
    relative = path.split(marker, 1)[1]
    root = Path(settings.UPLOAD_DIR).resolve()
    target = (root / relative).resolve()
    if root == target or root not in target.parents:
        return
    target.unlink(missing_ok=True)


def resolve_storage_key(storage_key: str) -> Path:
    root = Path(settings.UPLOAD_DIR).resolve()
    target = (root / storage_key).resolve()
    if root == target or root not in target.parents:
        raise ValueError("Invalid storage key")
    return target


def resolve_private_storage_key(storage_key: str) -> Path:
    root = Path(settings.PRIVATE_UPLOAD_DIR).resolve()
    target = (root / storage_key).resolve()
    if root == target or root not in target.parents:
        raise ValueError("Invalid private storage key")
    return target
