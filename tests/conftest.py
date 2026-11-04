import sys
import types

# يسمح بتشغيل اختبارات المنطق حتى لو httpx غير مثبّت (في CI يكون مثبّتًا فعليًا)
try:
    import httpx  # noqa: F401
except ImportError:  # pragma: no cover
    stub = types.ModuleType("httpx")
    stub.HTTPError = Exception
    stub.Timeout = lambda *a, **k: None
    stub.AsyncClient = lambda *a, **k: None
    sys.modules["httpx"] = stub
