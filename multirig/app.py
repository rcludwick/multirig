"""
MultiRig FastAPI application.

Main entry point for the web server. Sets up Zenoh session, routes,
and WebSocket endpoints.
"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse


from multirig.gateway.routes import router
from multirig.gateway.websocket import websocket_endpoint, ws_manager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for the application.
    
    Manages startup and shutdown of all MultiRig components:
    - Application manager (Zenoh, adapters, engines, servers)
    - WebSocket manager
    """
    from multirig.application import start_application, stop_application
    import os
    
    # Get profile from environment variable
    profile_name = os.getenv("MULTIRIG_PROFILE", "default")
    
    # Start application
    await start_application(profile_name=profile_name)
    
    # Start WebSocket manager
    await ws_manager.start()
    
    try:
        yield
    finally:
        # Cleanup on shutdown
        await ws_manager.stop()
        await stop_application()


# Create FastAPI application
app = FastAPI(
    title="MultiRig",
    description="Control and sync multiple ham radio rigs",
    version="0.2.0",
    lifespan=lifespan
)

# Include REST API routes
app.include_router(router)

# WebSocket endpoint
app.add_websocket_route("/ws", websocket_endpoint)

# Static files and frontend
STATIC_DIR = Path(__file__).parent / "static"

if STATIC_DIR.exists():
    # Serve static files
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    
    # Serve index.html at root
    @app.get("/")
    async def serve_frontend():
        """Serve the frontend application."""
        index_path = STATIC_DIR / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
        return {"message": "MultiRig API - Frontend not built yet"}
else:
    @app.get("/")
    async def root():
        """Root endpoint when static files not available."""
        return {
            "message": "MultiRig API",
            "version": "0.2.0",
            "docs": "/docs"
        }


def run():
    """Run the application using uvicorn."""
    import uvicorn
    uvicorn.run(
        "multirig.app:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info"
    )


if __name__ == "__main__":
    run()
