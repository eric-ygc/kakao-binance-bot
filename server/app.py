"""픽보조 관리 서버 — FastAPI 진입점"""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

from .database import init_db
from .routers import agent, dashboard, events

app = FastAPI(title="픽보조 관리 서버")

app.include_router(agent.router)
app.include_router(dashboard.router)
app.include_router(events.router)

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.on_event("startup")
def startup():
    init_db()


@app.get("/")
async def index():
    return FileResponse(str(STATIC_DIR / "index.html"))
