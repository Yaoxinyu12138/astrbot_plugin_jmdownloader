"""PDF 处理工具"""

import random
import struct


def modify_pdf_md5(original_pdf_path: str, output_path: str) -> bool:
    """修改 PDF 文件的 MD5 值"""
    try:
        with open(original_pdf_path, "rb") as f:
            content = f.read()

        random_bytes = struct.pack("d", random.random())

        if content.endswith(b"%%EOF"):
            modified_content = (
                content[:-5] + b"\n% Random: " + random_bytes + b"\n%%EOF"
            )
        else:
            modified_content = content + b"\n% Random: " + random_bytes + b"\n%%EOF"

        with open(output_path, "wb") as f:
            f.write(modified_content)

        return True
    except Exception:
        return False


async def modify_pdf_md5_async(original_pdf_path: str, output_path: str) -> bool:
    """异步版本的 modify_pdf_md5"""
    import asyncio

    return await asyncio.to_thread(modify_pdf_md5, original_pdf_path, output_path)


async def prepare_pdf_with_unique_md5(
    src_path: str,
    cache_dir: str,
    photo_id: str,
) -> str | None:
    """复制 PDF 并修改 MD5"""
    import hashlib
    import time
    from pathlib import Path

    random_suffix = hashlib.md5(
        str(time.time() + random.random()).encode()
    ).hexdigest()[:8]
    dest_path = Path(cache_dir) / f"{photo_id}_{random_suffix}.pdf"

    if await modify_pdf_md5_async(src_path, str(dest_path)):
        return str(dest_path)
    return None