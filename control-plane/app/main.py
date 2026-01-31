from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.router import api_router


def create_app():
    app = FastAPI(
        title="Elevator Ad Platform - Control Plane",
        version="0.1.0"
    )

    # ✅ 一定要在这里加 CORS（作用于整个 app）
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # expose both /api/v1 and /api for frontend compatibility
    app.include_router(api_router, prefix="/api/v1")
    app.include_router(api_router, prefix="/api")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False
    )
