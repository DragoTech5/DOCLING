"""
Docling Knowledge Hub - Main FastAPI Application
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

import os

from app.config import config, TEMPLATES_DIR, STATIC_DIR
from app.db.models import init_database
from app.services.settings_service import initialize_default_settings, load_settings_to_config
from app.services.scheduler_service import start_scheduler, stop_scheduler
from app.services.ssh_tunnel import init_tunnels, close_all_tunnels

# Import API routers
from app.api.categories import router as categories_router
from app.api.documents import router as documents_router
from app.api.youtube import router as youtube_router
from app.api.rumble import router as rumble_router
from app.api.websites import router as websites_router
from app.api.query import router as query_router
from app.api.jobs import router as jobs_router, worker_router
from app.api.settings import router as settings_router
from app.api.chat import router as chat_router
from app.api.auth import router as auth_router
from app.api.stripe_routes import router as stripe_router
from app.api.audio_files import router as audio_files_router
from app.api.magick_api import router as magick_router
from app.api.telegram import router as telegram_router
from app.api.admin import router as admin_router
from app.api.payments import router as payments_router

# Import middleware
from app.middleware.auth import AuthMiddleware, get_optional_user


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management."""
    # Startup
    print("Starting Docling Knowledge Hub...")

    # Show current mode
    mode = "PRIVATE" if config.mode.private_mode else "SAAS"
    auth_status = "disabled" if not config.mode.auth_required else "enabled"
    print(f"Mode: {mode} | Auth: {auth_status}")

    if config.weaviate.is_configured:
        print(f"Weaviate: enabled ({config.weaviate.host}:{config.weaviate.port})")
    else:
        print("Weaviate: disabled")

    if config.pgvector.enabled:
        print(f"pgvector: enabled ({config.pgvector.host}:{config.pgvector.port}/{config.pgvector.database})")

        # Initialize SSH tunnels if enabled
        if os.getenv("SSH_TUNNEL_ENABLED", "false").lower() == "true":
            nas_host = os.getenv("NAS_HOST", "192.168.1.117")
            nas_username = os.getenv("NAS_USERNAME", "kanat")
            nas_password = os.getenv("NAS_PASSWORD", "")
            try:
                init_tunnels(nas_host, nas_username, nas_password)
                print(f"SSH tunnels: enabled ({nas_host})")
            except Exception as e:
                print(f"Warning: Failed to initialize SSH tunnels: {e}")
    else:
        print("pgvector: disabled (set PGVECTOR_ENABLED=true to enable MAGICK PDFs API)")

    # Initialize database
    await init_database()

    # Initialize default settings
    await initialize_default_settings()

    # Load settings into runtime config
    await load_settings_to_config()

    # Start scheduler for channel monitoring
    start_scheduler()

    print(f"Server running on http://{config.server.host}:{config.server.port}")

    yield

    # Shutdown
    print("Shutting down...")
    stop_scheduler()

    # Close Weaviate client if configured
    if config.weaviate.is_configured:
        from app.lib.weaviate_client import close_weaviate_client
        close_weaviate_client()

    # Close pgvector connection pool if configured
    if config.pgvector.enabled:
        from app.services import pgvector_service
        await pgvector_service.close_pool()

        # Close SSH tunnels if enabled
        if os.getenv("SSH_TUNNEL_ENABLED", "false").lower() == "true":
            close_all_tunnels()


# Create FastAPI app
app = FastAPI(
    title="Docling Knowledge Hub",
    description="Document processing and knowledge management with RAG",
    version="0.1.0",
    lifespan=lifespan,
)

# Mount static files
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Mount book covers from NAS (for Telegram Mini App)
import pathlib
BCOVERS_DIR = pathlib.Path("/mnt/smb_terra/BCOVERS")
if BCOVERS_DIR.exists():
    app.mount("/covers/maglib", StaticFiles(directory=BCOVERS_DIR / "MAGICK-MATTERS"), name="covers_maglib")
    if (BCOVERS_DIR / "BiBLIOTHEK-LIBRARY").exists():
        app.mount("/covers/bibliothek", StaticFiles(directory=BCOVERS_DIR / "BiBLIOTHEK-LIBRARY"), name="covers_bibliothek")

# Mount Telegram Mini App (built frontend)
# Dockerfile copies frontend dist to /app/static/twa
import pathlib
TWA_DIST_DIR = pathlib.Path("/app") / "static" / "twa"
if TWA_DIST_DIR.exists():
    # Mount assets directory for JS/CSS files
    app.mount("/twa/assets", StaticFiles(directory=TWA_DIST_DIR / "assets"), name="twa_assets")

# Setup templates
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Add CORS middleware for Telegram Mini App
# Note: Telegram Mini App uses X-Telegram-Init-Data header, not cookies
import os
cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")
# Allow cloudflare tunnel origins for testing
cors_origins.extend([
    "https://playstation-vacuum-doom-desired.trycloudflare.com",
    "https://vessels-scholar-thunder-accuracy.trycloudflare.com",
])
# Also allow any trycloudflare.com subdomain for dynamic tunnels
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_origin_regex=r"https://.*\.trycloudflare\.com",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["X-Telegram-Init-Data", "Content-Type", "Authorization"],
    expose_headers=["*"],
)

# Add auth middleware (optional - works without Supabase configured)
app.add_middleware(AuthMiddleware)

# Include API routers
app.include_router(categories_router)
app.include_router(documents_router)
app.include_router(youtube_router)
app.include_router(rumble_router)
app.include_router(websites_router)
app.include_router(query_router)
app.include_router(jobs_router)
app.include_router(worker_router)
app.include_router(settings_router)
app.include_router(chat_router)
app.include_router(auth_router)
app.include_router(stripe_router)
app.include_router(audio_files_router)
app.include_router(magick_router)  # MAGICK PDFs API
app.include_router(telegram_router)  # Telegram Mini App API
app.include_router(admin_router)  # Admin Dashboard API (analytics)
app.include_router(payments_router)  # Dodo Payments API (credit cards)


# Telegram Mini App Routes (SPA)
@app.get("/twa")
@app.get("/twa/")
@app.get("/twa/{path:path}")
async def telegram_mini_app(path: str = ""):
    """Serve Telegram Mini App SPA with static file support.

    - Serves actual static files (images, favicons, etc.) from dist/
    - Serves index.html for SPA routes (chat, archive, share, etc.)
    This allows React Router to handle all SPA routing.
    """
    from fastapi.responses import FileResponse
    from pathlib import Path

    if not TWA_DIST_DIR.exists():
        return {"error": "Telegram Mini App not built. Run 'npm run build' in telegram-mini-app/"}

    # Check if the requested path is a static file
    if path:
        file_path = TWA_DIST_DIR / path
        if file_path.exists() and file_path.is_file():
            # Serve the actual file (image, favicon, etc.)
            return FileResponse(file_path)

    # For all other routes (SPA routes), serve index.html
    # This allows React Router to handle the routing
    index_file = TWA_DIST_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)

    return {"error": "Telegram Mini App index.html not found"}


# Web UI Routes
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Dashboard page."""
    return templates.TemplateResponse(
        "pages/dashboard.html",
        {"request": request, "title": "Dashboard"},
    )


@app.get("/ingest", response_class=HTMLResponse)
async def ingest_page(request: Request):
    """Ingestion page."""
    return templates.TemplateResponse(
        "pages/ingest.html",
        {"request": request, "title": "Ingest Content"},
    )


@app.get("/browse", response_class=HTMLResponse)
async def browse_page(request: Request):
    """Content browser page."""
    return templates.TemplateResponse(
        "pages/browse.html",
        {"request": request, "title": "Browse Content"},
    )


@app.get("/query", response_class=HTMLResponse)
async def query_page(request: Request):
    """Query interface page."""
    return templates.TemplateResponse(
        "pages/query.html",
        {"request": request, "title": "Query Knowledge Base"},
    )


@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    """Chat interface page."""
    return templates.TemplateResponse(
        "pages/chat.html",
        {"request": request, "title": "Chat with Knowledge Base"},
    )


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    """Settings page."""
    return templates.TemplateResponse(
        "pages/settings.html",
        {"request": request, "title": "Settings"},
    )


@app.get("/status", response_class=HTMLResponse)
async def status_page(request: Request):
    """System status page."""
    return templates.TemplateResponse(
        "pages/status.html",
        {"request": request, "title": "System Status"},
    )


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Login page."""
    return templates.TemplateResponse(
        "pages/login.html",
        {"request": request, "title": "Sign In"},
    )


@app.get("/pricing", response_class=HTMLResponse)
async def pricing_page(request: Request):
    """Pricing page."""
    from app.lib.stripe_client import PRICING
    return templates.TemplateResponse(
        "pages/pricing.html",
        {
            "request": request,
            "title": "Pricing",
            "pricing": PRICING,
            "stripe_configured": config.stripe.is_configured,
        },
    )


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "version": "0.1.0",
    }


# API documentation redirect
@app.get("/api", include_in_schema=False)
async def api_docs():
    """Redirect to API documentation."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/docs")
