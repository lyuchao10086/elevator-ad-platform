from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware # 必须导入
from app.api.v1.router import api_router

def create_app():
    app = FastAPI(title="Elevator Ad Platform - Control Plane", version="0.1.0")

    # 🌟 必须加上这段，否则前端 3000 端口无法访问后端 8000 端口
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"], # 开发环境允许所有来源，生产环境再改回具体域名
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix="/api/v1")
    app.include_router(api_router, prefix="/api")
    
    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app

app = create_app()


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)

