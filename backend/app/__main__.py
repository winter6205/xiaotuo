"""本地启动入口：uv run python -m app（端口与地址取自 PORT / HOST，默认 127.0.0.1:13773）。"""
import uvicorn

from app.config import settings

if __name__ == "__main__":
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, proxy_headers=True)
