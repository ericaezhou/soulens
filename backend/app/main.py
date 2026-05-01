from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.routes.analyze import router as analyze_router
from app.routes.edit import router as edit_router
from app.config import UPLOAD_DIR

app = FastAPI(
    title="Auto-Edit API",
    description="AI-powered Instagram Reel editor that replicates your style",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analyze_router)
app.include_router(edit_router)

# Serve uploaded files (for video preview)
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")


@app.get("/health")
async def health():
    return {"status": "ok"}
