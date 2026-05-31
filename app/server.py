"""FastAPI application with lifespan management."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import load_config, save_config
from .scheduler import start_scheduler, stop_scheduler
from .ftp_uploader import start_ftp_uploader, stop_ftp_uploader

BASE_DIR = Path(__file__).parent.parent
STATIC_DIR = Path(__file__).parent / "web" / "static"
TEMPLATES_DIR = Path(__file__).parent / "web" / "templates"

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    # Startup
    log_file = BASE_DIR / "app.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(str(log_file), encoding="utf-8"),
        ],
    )
    logger.info("Loading configuration...")
    config = load_config()
    app.state.config = config
    logger.info(f"Loaded {len(config.devices)} device(s)")

    # Ensure data directory exists
    data_dir = BASE_DIR / config.data_dir
    data_dir.mkdir(parents=True, exist_ok=True)

    # Start scheduler and FTP uploader
    await start_scheduler()
    await start_ftp_uploader()
    logger.info("Application started")

    yield

    # Shutdown
    logger.info("Application shutting down...")
    await stop_ftp_uploader()
    await stop_scheduler()
    logger.info("Shutdown complete")


app = FastAPI(
    title="工业数据采集系统",
    description="Modbus TCP / Siemens S7 设备数据采集与 FTP 上传",
    version="1.0.0",
    lifespan=lifespan,
)

# Mount static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Initialize templates
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Import and include routers
from .web.routes import router as web_router
from .web.api import router as api_router

app.include_router(web_router)
app.include_router(api_router)
