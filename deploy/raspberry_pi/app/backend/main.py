from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from backend.api.routes import app as api_app, lifespan

app = FastAPI(title="Home Automation", version="1.0.0", lifespan=lifespan)
app.mount("/api", api_app)
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")