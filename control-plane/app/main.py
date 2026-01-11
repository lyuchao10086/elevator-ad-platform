from fastapi import FastAPI
import uvicorn
import os

from app.api.v1.endpoints import devices


def create_app():
    app = FastAPI(title="control-plane")
    app.include_router(devices.router, prefix="/api/v1/devices")
    return app


app = create_app()


if __name__ == "__main__":
    # ensure snapshot dir exists
    try:
        from app.core.config import settings
        os.makedirs(settings.snapshot_storage_dir, exist_ok=True)
    except Exception:
        pass

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
