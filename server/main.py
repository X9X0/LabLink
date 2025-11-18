"""LabLink Server - Main application entry point."""

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

# Add shared directory to Python path
shared_path = Path(__file__).parent.parent / "shared"
sys.path.insert(0, str(shared_path))

from api import (acquisition_router, alarms_router, analysis_router,
                 backup_router, calibration_enhanced_router,
                 calibration_router, data_router, database_router,
                 diagnostics_router, discovery_router, equipment_router,
                 firmware_router, locks_router, performance_router,
                 profiles_router, safety_router, scheduler_router,
                 security_router, state_router, testing_router,
                 waveform_router)
from config.settings import settings
from config.validator import validate_config
from logging_config import LoggingMiddleware, get_logger, setup_logging
from web.routes import register_web_routes
from websocket_server import handle_websocket

# Setup advanced logging system
setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("=" * 70)
    logger.info(f"LabLink Server v0.27.0 - {settings.server_name}")
    logger.info("=" * 70)

    # Validate configuration
    logger.info("Validating configuration...")
    if not validate_config():
        logger.error("Configuration validation failed!")
        sys.exit(1)

    logger.info(f"API Port: {settings.api_port}")
    logger.info(f"WebSocket Port: {settings.ws_port}")
    logger.info(f"Log Level: {settings.log_level}")
    logger.info(
        f"Auto-reconnect: {'enabled' if settings.enable_auto_reconnect else 'disabled'}"
    )
    logger.info(
        f"Health monitoring: {'enabled' if settings.enable_health_monitoring else 'disabled'}"
    )
    logger.info(
        f"Equipment profiles: {'enabled' if settings.enable_profiles else 'disabled'}"
    )
    logger.info(
        f"Safety limits: {'enabled' if settings.enable_safety_limits else 'disabled'}"
    )
    logger.info(
        f"Safe state on disconnect: {'enabled' if settings.safe_state_on_disconnect else 'disabled'}"
    )
    logger.info(
        f"Equipment locks: {'enabled' if settings.enable_equipment_locks else 'disabled'}"
    )
    logger.info(
        f"Lock timeout: {settings.lock_timeout_sec}s, Session timeout: {settings.session_timeout_sec}s"
    )

    # Initialize equipment manager
    from equipment.manager import equipment_manager

    logger.info("Initializing equipment manager...")
    await equipment_manager.initialize()

    # Auto-register mock equipment if enabled
    if settings.enable_mock_equipment:
        logger.info("Mock equipment enabled - registering mock devices...")
        from equipment.mock_helper import MockEquipmentHelper

        try:
            equipment_ids = await MockEquipmentHelper.register_default_mock_equipment(
                equipment_manager
            )
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

    state_dir = settings.state_dir if hasattr(settings, "state_dir") else "./states"
    state_manager.set_state_directory(state_dir)
    if (
        settings.enable_state_persistence
        if hasattr(settings, "enable_state_persistence")
        else True
    ):
        state_manager.load_states_from_disk()

    # Initialize acquisition manager
    from acquisition import acquisition_manager

    acq_export_dir = (
        settings.acquisition_export_dir
        if hasattr(settings, "acquisition_export_dir")
        else "./data/acquisitions"
    )
    acquisition_manager.set_export_directory(acq_export_dir)

    # Start scheduler with persistence (v0.14.0)
    from scheduler import initialize_scheduler_manager

    logger.info("Initializing scheduler with persistence...")
    sched_db_path = (
        settings.scheduler_db_path
        if hasattr(settings, "scheduler_db_path")
        else "data/scheduler.db"
    )
    scheduler_manager = initialize_scheduler_manager(sched_db_path)
    await scheduler_manager.start()
    logger.info("Scheduler started with SQLite persistence")

    # Initialize equipment-alarm integrator
    from alarm import alarm_manager, initialize_integrator

    logger.info("Initializing equipment-alarm integrator...")
    integrator = initialize_integrator(equipment_manager, alarm_manager)
    await integrator.start_monitoring()
    logger.info("Equipment-alarm monitoring started")

    # Wire alarm manager to WebSocket stream manager for real-time notifications
    from websocket_server import stream_manager
    alarm_manager.set_stream_manager(stream_manager)
    logger.info("Alarm manager connected to WebSocket for real-time notifications")

    # Wire scheduler manager to WebSocket stream manager for real-time notifications
    scheduler_manager.set_stream_manager(stream_manager)
    logger.info("Scheduler manager connected to WebSocket for real-time notifications")

    # Initialize calibration manager (v0.12.0)
    from equipment.calibration import initialize_calibration_manager

    logger.info("Initializing calibration manager...")
    cal_storage_path = (
        settings.calibration_storage_path
        if hasattr(settings, "calibration_storage_path")
        else "data/calibration"
    )
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
    perf_db_path = (
        settings.performance_db_path
        if hasattr(settings, "performance_db_path")
        else "data/performance.db"
    )
    perf_monitor = initialize_performance_monitor(perf_db_path)
    logger.info("Performance monitoring system initialized")

    # Initialize waveform manager (v0.16.0)
    if settings.enable_waveform_analysis:
        from api.waveform import init_waveform_api
        from waveform.manager import WaveformManager

        logger.info("Initializing waveform capture & analysis system...")
        waveform_manager = WaveformManager(equipment_manager)
        init_waveform_api(waveform_manager)
        logger.info(
            "Waveform system initialized - 30+ measurements, math channels, persistence, XY mode enabled"
        )

    # Initialize database manager (v0.18.0)
    from database import initialize_database_manager

    logger.info("Initializing database integration...")
    db_path = (
        settings.database_path
        if hasattr(settings, "database_path")
        else "data/lablink.db"
    )
    db_manager = initialize_database_manager(db_path)
    logger.info(
        "Database initialized - Command logging, measurement archival, usage tracking enabled"
    )

    # Initialize enhanced calibration manager (v0.19.0)
    from equipment.calibration_enhanced import \
        initialize_enhanced_calibration_manager

    logger.info("Initializing enhanced calibration system...")
    enhanced_cal_path = (
        settings.calibration_enhanced_path
        if hasattr(settings, "calibration_enhanced_path")
        else "data/calibration_enhanced"
    )
    enhanced_cal_manager = initialize_enhanced_calibration_manager(enhanced_cal_path)
    logger.info(
        "Enhanced calibration initialized - Procedures, certificates, corrections, standards tracking enabled"
    )

    # Initialize test executor (v0.20.0)
    from testing import initialize_test_executor

    logger.info("Initializing automated test sequences...")
    test_executor = initialize_test_executor(equipment_manager, db_manager)
    logger.info(
        "Test automation initialized - Sequences, sweeps, validation, templates enabled"
    )

    # Initialize backup manager (v0.21.0)
    from backup import BackupConfig, CompressionType, initialize_backup_manager

    logger.info("Initializing backup & restore system...")
    backup_config = BackupConfig(
        backup_dir=settings.backup_dir,
        enable_auto_backup=settings.enable_auto_backup,
        auto_backup_interval_hours=settings.auto_backup_interval_hours,
        retention_days=settings.backup_retention_days,
        max_backup_count=settings.max_backup_count,
        include_config=settings.backup_include_config,
        include_profiles=settings.backup_include_profiles,
        include_states=settings.backup_include_states,
        include_database=settings.backup_include_database,
        include_acquisitions=settings.backup_include_acquisitions,
        include_logs=settings.backup_include_logs,
        include_calibration=settings.backup_include_calibration,
        compression=CompressionType(settings.backup_compression),
        verify_after_backup=settings.backup_verify_after_creation,
        calculate_checksums=settings.backup_calculate_checksums,
    )
    backup_manager = initialize_backup_manager(backup_config)
    await backup_manager.start_auto_backup()
    logger.info(
        "Backup system initialized - Auto-backup, verification, retention policy enabled"
    )

    # Initialize discovery manager (v0.22.0)
    if settings.enable_discovery:
        from discovery import DiscoveryConfig, initialize_discovery_manager

        logger.info("Initializing equipment discovery system...")
        discovery_config = DiscoveryConfig(
            enable_mdns=settings.enable_mdns_discovery,
            enable_visa_scan=settings.enable_visa_discovery,
            enable_usb_scan=settings.enable_usb_discovery,
            enable_auto_discovery=settings.enable_auto_discovery,
            mdns_scan_interval_sec=settings.mdns_scan_interval_sec,
            visa_scan_interval_sec=settings.visa_scan_interval_sec,
            scan_tcpip=settings.discovery_scan_tcpip,
            scan_usb=settings.discovery_scan_usb,
            scan_gpib=settings.discovery_scan_gpib,
            scan_serial=settings.discovery_scan_serial,
            test_connections=settings.discovery_test_connections,
            query_idn=settings.discovery_query_idn,
            enable_history=settings.discovery_enable_history,
            history_retention_days=settings.discovery_history_retention_days,
            enable_recommendations=settings.discovery_enable_recommendations,
            cache_discovered_devices=settings.discovery_cache_devices,
            cache_ttl_sec=settings.discovery_cache_ttl_sec,
        )
        discovery_manager = initialize_discovery_manager(
            discovery_config, settings.visa_backend
        )
        await discovery_manager.start_auto_discovery()
        logger.info(
            "Discovery system initialized - Auto-discovery, mDNS, VISA scanning, smart recommendations enabled"
        )

    # Initialize security system (v0.23.0)
    if settings.enable_advanced_security:
        from security import (AuthConfig, generate_secure_secret_key,
                              init_security_manager)

        logger.info("Initializing advanced security system...")

        # Generate or use configured JWT secret
        jwt_secret = settings.jwt_secret_key or generate_secure_secret_key()

        auth_config = AuthConfig(
            secret_key=jwt_secret,
            algorithm=settings.jwt_algorithm,
            access_token_expire_minutes=settings.jwt_access_token_expire_minutes,
            refresh_token_expire_days=settings.jwt_refresh_token_expire_days,
            max_failed_login_attempts=settings.max_failed_login_attempts,
            account_lockout_duration_minutes=settings.account_lockout_duration_minutes,
            require_password_change_days=settings.password_expiration_days,
        )

        security_manager = init_security_manager(settings.security_db_path, auth_config)

        # Create default admin user if enabled
        if settings.create_default_admin:
            from security import UserCreate

            try:
                admin_user = await security_manager.get_user_by_username(
                    settings.default_admin_username
                )
                if not admin_user:
                    # Get admin role
                    admin_role = security_manager.get_role_by_name("admin")
                    admin_user = await security_manager.create_user(
                        UserCreate(
                            username=settings.default_admin_username,
                            email=settings.default_admin_email,
                            password=settings.default_admin_password,
                            full_name="Default Administrator",
                            roles=[admin_role.role_id] if admin_role else [],
                            must_change_password=True,
                        ),
                        created_by=None,
                    )
                    admin_user.is_superuser = True

                    # Update superuser flag in database
                    from datetime import datetime
                    from sqlite3 import connect

                    conn = connect(str(security_manager.db_path))
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        UPDATE users SET is_superuser = 1, updated_at = ? WHERE user_id = ?
                    """,
                        (datetime.utcnow(), admin_user.user_id),
                    )
                    conn.commit()
                    conn.close()

                    logger.warning(
                        f"⚠️  DEFAULT ADMIN CREATED - Username: {settings.default_admin_username}, Password: {settings.default_admin_password}"
                    )
                    logger.warning("⚠️  CHANGE THE DEFAULT PASSWORD IMMEDIATELY!")
                else:
                    logger.info(
                        f"Default admin user already exists: {settings.default_admin_username}"
                    )
            except Exception as e:
                logger.error(f"Failed to create default admin user: {e}")

        logger.info(
            "Advanced security initialized - JWT auth, RBAC, API keys, IP whitelisting, audit logging enabled"
        )

        # Initialize OAuth2 providers if enabled (v0.25.0)
        if settings.enable_oauth2:
            from security import (OAUTH2_DEFAULTS, OAuth2Config,
                                  OAuth2Provider, init_oauth2_manager)

            logger.info("Initializing OAuth2 authentication providers...")

            oauth2_configs = []

            # Google OAuth2
            if (
                settings.oauth2_google_enabled
                and settings.oauth2_google_client_id
                and settings.oauth2_google_client_secret
            ):
                google_defaults = OAUTH2_DEFAULTS[OAuth2Provider.GOOGLE]
                oauth2_configs.append(
                    OAuth2Config(
                        provider=OAuth2Provider.GOOGLE,
                        client_id=settings.oauth2_google_client_id,
                        client_secret=settings.oauth2_google_client_secret,
                        authorization_url=google_defaults["authorization_url"],
                        token_url=google_defaults["token_url"],
                        user_info_url=google_defaults["user_info_url"],
                        scopes=google_defaults["scopes"],
                        enabled=True,
                    )
                )
                logger.info("  - Google OAuth2 enabled")

            # GitHub OAuth2
            if (
                settings.oauth2_github_enabled
                and settings.oauth2_github_client_id
                and settings.oauth2_github_client_secret
            ):
                github_defaults = OAUTH2_DEFAULTS[OAuth2Provider.GITHUB]
                oauth2_configs.append(
                    OAuth2Config(
                        provider=OAuth2Provider.GITHUB,
                        client_id=settings.oauth2_github_client_id,
                        client_secret=settings.oauth2_github_client_secret,
                        authorization_url=github_defaults["authorization_url"],
                        token_url=github_defaults["token_url"],
                        user_info_url=github_defaults["user_info_url"],
                        scopes=github_defaults["scopes"],
                        enabled=True,
                    )
                )
                logger.info("  - GitHub OAuth2 enabled")

            # Microsoft OAuth2
            if (
                settings.oauth2_microsoft_enabled
                and settings.oauth2_microsoft_client_id
                and settings.oauth2_microsoft_client_secret
            ):
                microsoft_defaults = OAUTH2_DEFAULTS[OAuth2Provider.MICROSOFT]
                oauth2_configs.append(
                    OAuth2Config(
                        provider=OAuth2Provider.MICROSOFT,
                        client_id=settings.oauth2_microsoft_client_id,
                        client_secret=settings.oauth2_microsoft_client_secret,
                        authorization_url=microsoft_defaults["authorization_url"],
                        token_url=microsoft_defaults["token_url"],
                        user_info_url=microsoft_defaults["user_info_url"],
                        scopes=microsoft_defaults["scopes"],
                        enabled=True,
                    )
                )
                logger.info("  - Microsoft OAuth2 enabled")

            if oauth2_configs:
                oauth2_manager = init_oauth2_manager(oauth2_configs)
                logger.info(
                    f"OAuth2 initialized with {len(oauth2_configs)} provider(s)"
                )
            else:
                logger.warning("OAuth2 enabled but no providers configured")

    else:
        logger.info("Advanced security disabled")

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

    # Stop backup auto-backup task
    from backup import get_backup_manager

    backup_manager = get_backup_manager()
    await backup_manager.stop_auto_backup()
    logger.info("Backup auto-backup task stopped")

    # Stop discovery auto-discovery task
    if settings.enable_discovery:
        from discovery import get_discovery_manager

        discovery_manager = get_discovery_manager()
        await discovery_manager.stop_auto_discovery()
        logger.info("Discovery auto-discovery task stopped")

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
    version="0.27.0",
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

# Register web routes (static files and HTML templates)
register_web_routes(app)

# Include API routers
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
app.include_router(waveform_router, tags=["waveform"])
app.include_router(analysis_router, tags=["analysis"])
app.include_router(database_router, tags=["database"])
app.include_router(calibration_enhanced_router, tags=["calibration-enhanced"])
app.include_router(testing_router, tags=["testing"])
app.include_router(backup_router, tags=["backup"])
app.include_router(discovery_router, tags=["discovery"])
app.include_router(security_router, tags=["security"])
app.include_router(firmware_router, tags=["firmware"])


@app.get("/api")
async def api_root():
    """API root endpoint."""
    return {
        "name": "LabLink Server",
        "version": "0.27.0",
        "status": "running",
        "security_enabled": settings.enable_advanced_security,
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
