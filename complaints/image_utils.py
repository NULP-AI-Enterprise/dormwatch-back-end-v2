import uuid
from io import BytesIO
from PIL import Image, ImageOps
from django.core.files.base import ContentFile

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_PIXELS = 25_000_000


def process_complaint_photo(uploaded_file):
    if getattr(uploaded_file, "content_type", "") not in ALLOWED_CONTENT_TYPES:
        raise ValueError("Unsupported image format")

    img = Image.open(uploaded_file)
    img = ImageOps.exif_transpose(img)

    if img.width * img.height > MAX_PIXELS:
        raise ValueError("Image dimensions too large")

    exif_data = img.info.get("exif")

    img.thumbnail((2048, 2048), Image.LANCZOS)
    full_buf = BytesIO()
    save_kwargs = {"format": "WEBP", "quality": 80, "method": 6}
    if exif_data:
        save_kwargs["exif"] = exif_data
    img.save(full_buf, **save_kwargs)
    full_buf.seek(0)

    img.thumbnail((400, 400), Image.LANCZOS)
    thumb_buf = BytesIO()
    img.save(thumb_buf, format="WEBP", quality=80, method=6)
    thumb_buf.seek(0)

    file_id = uuid.uuid4().hex
    full_filename = f"{file_id}.webp"
    thumbnail_filename = f"thumb_{file_id}.webp"

    full_content = ContentFile(full_buf.getvalue(), name=full_filename)
    thumb_content = ContentFile(thumb_buf.getvalue(), name=thumbnail_filename)
    full_buf.close()
    thumb_buf.close()

    return {
        "full": full_content,
        "thumbnail": thumb_content,
        "full_filename": full_filename,
        "thumbnail_filename": thumbnail_filename,
    }
