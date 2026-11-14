"""Greenlight API. Owner: Split B (shell). Do NOT add endpoints here —
add them to your own file in app/routers/. This file only wires routers."""
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

load_dotenv()

from .routers import check, intake, assist, extras, pack  # noqa: E402

app = FastAPI(title="Greenlight")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

app.include_router(check.router, prefix="/api")   # Split B
app.include_router(intake.router, prefix="/api")  # Split A
app.include_router(assist.router, prefix="/api")  # Split A
app.include_router(extras.router, prefix="/api")  # Split B
app.include_router(pack.router, prefix="/api")    # Split B


@app.get("/api/health")
def health():
    return {"ok": True}


# In production (Replit) serve the built frontend from the same server.
DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if DIST.exists():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="frontend")
