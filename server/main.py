"""LabLink Server - Main application entry point."""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from config.settings import settings
from api import equipment_router, data_router
from websocket_server import handle_websocket

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("LabLink Server starting...")
    logger.info(f"API Port: {settings.api_port}")
    logger.info(f"WebSocket Port: {settings.ws_port}")

    # Initialize equipment manager
    from equipment.manager import equipment_manager
    await equipment_manager.initialize()

    yield

    # Cleanup
    logger.info("LabLink Server shutting down...")
    await equipment_manager.shutdown()


# Create FastAPI application
app = FastAPI(
    title="LabLink Server",
    description="Remote control and data acquisition for lab equipment",
    version="0.1.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(equipment_router, prefix="/api/equipment", tags=["equipment"])
app.include_router(data_router, prefix="/api/data", tags=["data"])


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "LabLink Server",
        "version": "0.1.0",
        "status": "running",
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    from equipment.manager import equipment_manager
    return {
        "status": "healthy",
        "connected_devices": len(equipment_manager.get_connected_devices()),
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time data streaming."""
    await handle_websocket(websocket)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.api_port,
        reload=settings.debug,
        log_level="debug" if settings.debug else "info",
    )
