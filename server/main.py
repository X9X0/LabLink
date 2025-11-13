"""LabLink Server - Main application entry point."""

import logging
import sys
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

# Add shared directory to Python path
shared_path = Path(__file__).parent.parent / "shared"
sys.path.insert(0, str(shared_path))

from config.settings import settings
from config.validator import validate_config
from api import equipment_router, data_router, profiles_router, safety_router, locks_router, state_router, acquisition_router, alarms_router, scheduler_router, diagnostics_router, calibration_router, performance_router
from websocket_server import handle_websocket
from logging_config import setup_logging, LoggingMiddleware, get_logger

# Setup advanced logging system
setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("=" * 70)
    logger.info(f"LabLink Server v0.13.0 - {settings.server_name}")
    logger.info("=" * 70)

    # Validate configuration
    logger.info("Validating configuration...")
    if not validate_config():
        logger.error("Configuration validation failed!")
        sys.exit(1)

    logger.info(f"API Port: {settings.api_port}")
    logger.info(f"WebSocket Port: {settings.ws_port}")
    logger.info(f"Log Level: {settings.log_level}")
    logger.info(f"Auto-reconnect: {'enabled' if settings.enable_auto_reconnect else 'disabled'}")
    logger.info(f"Health monitoring: {'enabled' if settings.enable_health_monitoring else 'disabled'}")
    logger.info(f"Equipment profiles: {'enabled' if settings.enable_profiles else 'disabled'}")
    logger.info(f"Safety limits: {'enabled' if settings.enable_safety_limits else 'disabled'}")
    logger.info(f"Safe state on disconnect: {'enabled' if settings.safe_state_on_disconnect else 'disabled'}")
    logger.info(f"Equipment locks: {'enabled' if settings.enable_equipment_locks else 'disabled'}")
    logger.info(f"Lock timeout: {settings.lock_timeout_sec}s, Session timeout: {settings.session_timeout_sec}s")

    # Initialize equipment manager
    from equipment.manager import equipment_manager
    logger.info("Initializing equipment manager...")
    await equipment_manager.initialize()

    # Auto-register mock equipment if enabled
    if settings.enable_mock_equipment:
        logger.info("Mock equipment enabled - registering mock devices...")
        from equipment.mock_helper import MockEquipmentHelper
        try:
            equipment_ids = await MockEquipmentHelper.register_default_mock_equipment(equipment_manager)
            logger.info(f"Registered {len(equipment_ids)} mock equipment devices")
            for equipment_id in equipment_ids:
                equipment = equipment_manager.equipment.get(equipment_id)
                if equipment:
                    info = await equipment.get_info()
                    logger.info(f"  - {info.model} ({info.type.value}): {equipment_id}")
        except Exception as e:
            logger.error(f"Failed to register mock equipment: {e}")

    # Start health monitoring
    from equipment.error_handler import health_monitor
    await health_monitor.start(equipment_manager)

    # Create default profiles
    from equipment.profiles import create_default_profiles
    create_default_profiles()

    # Start lock cleanup task
    from equipment.locks import lock_manager
    await lock_manager.start_cleanup_task()

    # Initialize state manager
    from equipment.state import state_manager
    state_dir = settings.state_dir if hasattr(settings, 'state_dir') else "./states"
    state_manager.set_state_directory(state_dir)
    if settings.enable_state_persistence if hasattr(settings, 'enable_state_persistence') else True:
        state_manager.load_states_from_disk()

    # Initialize acquisition manager
    from acquisition import acquisition_manager
    acq_export_dir = settings.acquisition_export_dir if hasattr(settings, 'acquisition_export_dir') else "./data/acquisitions"
    acquisition_manager.set_export_directory(acq_export_dir)

    # Start scheduler
    from scheduler import scheduler_manager
    await scheduler_manager.start()

    # Initialize equipment-alarm integrator
    from alarm import alarm_manager, initialize_integrator
    logger.info("Initializing equipment-alarm integrator...")
    integrator = initialize_integrator(equipment_manager, alarm_manager)
    await integrator.start_monitoring()
    logger.info("Equipment-alarm monitoring started")

    # Initialize calibration manager (v0.12.0)
    from equipment.calibration import initialize_calibration_manager
    logger.info("Initializing calibration manager...")
    cal_storage_path = settings.calibration_storage_path if hasattr(settings, 'calibration_storage_path') else "data/calibration"
    calibration_manager = initialize_calibration_manager(cal_storage_path)
    logger.info("Calibration manager initialized")

    # Initialize error code database (v0.12.0)
    from equipment.error_codes import initialize_error_code_db
    logger.info("Initializing error code database...")
    error_db = initialize_error_code_db()
    logger.info("Error code database initialized")

    # Initialize performance monitor (v0.13.0)
    from performance import initialize_performance_monitor
    logger.info("Initializing performance monitoring system...")
    perf_db_path = settings.performance_db_path if hasattr(settings, 'performance_db_path') else "data/performance.db"
    perf_monitor = initialize_performance_monitor(perf_db_path)
    logger.info("Performance monitoring system initialized")

    logger.info("=" * 70)
    logger.info("LabLink Server ready!")
    logger.info("=" * 70)

    yield

    # Cleanup
    logger.info("LabLink Server shutting down...")

    # Stop equipment-alarm integrator
    from alarm import get_integrator
    integrator = get_integrator()
    if integrator:
        await integrator.stop_monitoring()
        logger.info("Equipment-alarm monitoring stopped")

    # Stop scheduler
    from scheduler import scheduler_manager
    await scheduler_manager.shutdown()

    # Stop lock cleanup task
    from equipment.locks import lock_manager
    await lock_manager.stop_cleanup_task()

    # Stop health monitoring
    from equipment.error_handler import health_monitor
    await health_monitor.stop()

    # Shutdown equipment manager
    await equipment_manager.shutdown()

    logger.info("Shutdown complete")


# Create FastAPI application
app = FastAPI(
    title="LabLink Server",
    description="Remote control and data acquisition for lab equipment",
    version="0.13.0",
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

# Add logging middleware
app.add_middleware(LoggingMiddleware)

# Include routers
app.include_router(equipment_router, prefix="/api/equipment", tags=["equipment"])
app.include_router(data_router, prefix="/api/data", tags=["data"])
app.include_router(profiles_router, prefix="/api/profiles", tags=["profiles"])
app.include_router(safety_router, prefix="/api/safety", tags=["safety"])
app.include_router(locks_router, prefix="/api", tags=["locks"])
app.include_router(state_router, prefix="/api", tags=["state"])
app.include_router(acquisition_router, prefix="/api/acquisition", tags=["acquisition"])
app.include_router(alarms_router, prefix="/api", tags=["alarms"])
app.include_router(scheduler_router, prefix="/api", tags=["scheduler"])
app.include_router(diagnostics_router, prefix="/api", tags=["diagnostics"])
app.include_router(calibration_router, prefix="/api", tags=["calibration"])
app.include_router(performance_router, prefix="/api", tags=["performance"])


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "LabLink Server",
        "version": "0.13.0",
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
