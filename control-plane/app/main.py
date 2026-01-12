from fastapi import FastAPI
from app.api.v1.router import api_router


def create_app():
    app = FastAPI(title="Elevator Ad Platform - Control Plane", version="0.1.0")
    app.include_router(api_router, prefix="/api/v1")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)

