from fastapi import FastAPI
from .routers import documents_router, query_router
from .telemetry import init_telemetry

def create_app() -> FastAPI:
    #initialize telemetry
    init_telemetry()

    application = FastAPI(title="RAG Service")
    application.include_router(query_router, prefix="/api/v1")
    application.include_router(documents_router, prefix="/api/v1")

    

    @application.get("/")
    def root():
        return {"service": "ragservice", "status": "ok"}

    @application.get("/health")
    def health():
        return {"status": "ok"}

    return application


app = create_app()