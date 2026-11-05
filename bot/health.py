"""خادم صحة صغير جدًا: بعض الاستضافات المجانية تتوقع أن التطبيق يفتح بورتًا (PORT).
لا يعمل إلا لو متغير PORT موجود، ولا يؤثر على التشغيل المحلي."""
from __future__ import annotations

import asyncio
import os

_RESPONSE = (
    b"HTTP/1.1 200 OK\r\nContent-Type: text/plain; charset=utf-8\r\n"
    b"Content-Length: 2\r\nConnection: close\r\n\r\nok"
)


async def _handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        await asyncio.wait_for(reader.read(1024), 5)
        writer.write(_RESPONSE)
        await writer.drain()
    except Exception:  # noqa: BLE001
        pass
    finally:
        writer.close()


async def start_health_server() -> asyncio.AbstractServer | None:
    port = os.getenv("PORT", "").strip()
    if not port.isdigit():
        return None
    return await asyncio.start_server(_handle, "0.0.0.0", int(port))
