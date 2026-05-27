"""图片处理工具"""

from __future__ import annotations

from io import BytesIO
from typing import IO

from PIL import Image


async def blur_image_async(image_data: bytes | IO) -> BytesIO:
    """对图片进行模糊处理"""
    if hasattr(image_data, 'read'):
        image_data = image_data.read()

    img = Image.open(BytesIO(image_data))

    # 模糊处理
    img = img.filter(Image.ModeFilter(mode=Image.FILTER_BLUR))

    output = BytesIO()
    img.save(output, format='JPEG', quality=85)
    output.seek(0)
    return output


async def resize_image(image_data: bytes | IO, max_size: int = 800) -> BytesIO:
    """调整图片大小"""
    if hasattr(image_data, 'read'):
        image_data = image_data.read()

    img = Image.open(BytesIO(image_data))

    # 等比缩放
    width, height = img.size
    if max(width, height) > max_size:
        ratio = max_size / max(width, height)
        new_size = (int(width * ratio), int(height * ratio))
        img = img.resize(new_size, Image.Resampling.LANCZOS)

    output = BytesIO()
    img.save(output, format='JPEG', quality=85)
    output.seek(0)
    return output