"""FastAPI application with lifespan management."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import load_config
from .scheduler import start_scheduler, stop_scheduler, set_pipeline
from .status_tracker import DeviceStatusTracker
from .pipeline import DataPipeline, make_file_writer
from .ftp_uploader import start_ftp_uploader, stop_ftp_uploader
from .upload_scheduler import start_upload_scheduler, stop_upload_scheduler
from .upload_executor import JsonFileConfigReader

BASE_DIR = Path(__file__).parent.parent
STATIC_DIR = Path(__file__).parent / "web" / "static"
TEMPLATES_DIR = Path(__file__).parent / "web" / "templates"

logger = logging.getLogger(__name__)

_pipeline: DataPipeline | None = None


def get_pipeline() -> DataPipeline:
    """Accessor for the DataPipeline instance (used by API endpoints)."""
    if _pipeline is None:
        raise RuntimeError("DataPipeline not initialized")
    return _pipeline


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

    # Wire up DataPipeline and inject into scheduler
    global _pipeline
    config_reader = JsonFileConfigReader()
    app_config = config_reader.get_app_config()
    data_dir = BASE_DIR / app_config.data_dir
    status_tracker = DeviceStatusTracker()
    data_writer = make_file_writer(data_dir)
    _pipeline = DataPipeline(
        status_tracker=status_tracker,
        config_reader=config_reader,
        data_writer=data_writer,
    )
    set_pipeline(_pipeline)

    # Start scheduler and FTP uploader
    await start_scheduler()
    await start_ftp_uploader()
    await start_upload_scheduler()
    logger.info("Application started")

    yield

    # Shutdown
    logger.info("Application shutting down...")
    await stop_upload_scheduler()
    await stop_ftp_uploader()
    await stop_scheduler()
    await _pipeline.shutdown()
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
