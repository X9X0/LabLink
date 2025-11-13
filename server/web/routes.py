"""Web dashboard routes for LabLink server."""

from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

# Get web directory path
WEB_DIR = Path(__file__).parent
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"

# Create router
router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def index():
    """Serve the main dashboard page."""
    return FileResponse(TEMPLATES_DIR / "dashboard.html")


@router.get("/login.html", response_class=HTMLResponse)
async def login_page():
    """Serve the login page."""
    return FileResponse(TEMPLATES_DIR / "login.html")


@router.get("/dashboard.html", response_class=HTMLResponse)
async def dashboard_page():
    """Serve the dashboard page."""
    return FileResponse(TEMPLATES_DIR / "dashboard.html")


@router.get("/profiles.html", response_class=HTMLResponse)
async def profiles_page():
    """Serve the profiles management page."""
    return FileResponse(TEMPLATES_DIR / "profiles.html")


def register_web_routes(app):
    """Register web routes and static files with the FastAPI app."""
    # Mount static files
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # Include web routes (after mounting static files)
    app.include_router(router, tags=["web"])
