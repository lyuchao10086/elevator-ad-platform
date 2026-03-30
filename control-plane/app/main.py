from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles # 【新增】
import os # 【新增】
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.router import api_router
from app.services.background_tasks import get_task_manager
import logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage application lifecycle: startup and shutdown events.
    """
    # Startup
    logger.info("Starting control-plane application...")
    task_manager = get_task_manager()
    
    # Start Kafka consumer background task
    try:
        # Try to start Kafka consumer
        # If it fails, continue running the app (Kafka is optional for API functionality)
        task_manager.start_kafka_consumer()
    except Exception as e:
        logger.warning(f"Failed to start Kafka consumer: {e}. App will continue without log ingestion.")
    
    yield
    
    # Shutdown
    logger.info("Shutting down control-plane application...")
    task_manager.stop_kafka_consumer()
    logger.info("Shutdown complete")


def create_app():
    app = FastAPI(
        title="Elevator Ad Platform - Control Plane",
        version="0.1.0",
        lifespan=lifespan
    )
    # 1. 获取 main.py 所在的 app 目录的绝对路径
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 2. 计算出上一级 storage/materials 的绝对路径
    # os.path.join 会处理好不同系统的路径斜杠问题
    materials_path = os.path.normpath(os.path.join(current_dir, "..", "storage", "materials"))
    
    # 3. 自动创建目录（如果不存在），防止程序因为找不到文件夹而崩溃
    os.makedirs(materials_path, exist_ok=True)
    
    # 打印一下路径，方便你在黑窗口（终端）里核对是否正确
    print(f"静态资源目录已挂载: {materials_path}")

    # 4. 挂载静态文件服务
    # 访问 http://127.0.0.1:8000/static/xxx 就会去上面的 materials_path 找文件
    app.mount("/static", StaticFiles(directory=materials_path), name="static")    
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
    app.include_router(api_router, prefix="/api",include_in_schema=False) #兼容用， 但Swagger不展示

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
