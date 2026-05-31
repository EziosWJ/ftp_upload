"""Main entry point for the industrial data collection system."""

import uvicorn
from app.server import app

if __name__ == "__main__":
    uvicorn.run(
        "app.server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
