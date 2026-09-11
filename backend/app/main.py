"""FastAPI application entry point and HTML frontend routes."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from backend.app.api.routes.documents import router as documents_router
from backend.app.core.config import PROJECT_ROOT, get_settings
from backend.app.core.database import init_database
from backend.app.core.exceptions import AppError
from backend.app.core.logging_config import configure_logging


configure_logging()
logger = logging.getLogger(__name__)
settings = get_settings()
templates = Jinja2Templates(directory=str(PROJECT_ROOT / "frontend" / "templates"))


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_database()
    logger.info("Application started", extra={"environment": settings.environment})
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Grounded extraction and financial validation for invoices and statements.",
    lifespan=lifespan,
)
app.include_router(documents_router)
app.mount(
    "/static",
    StaticFiles(directory=str(PROJECT_ROOT / "frontend" / "static")),
    name="static",
)


@app.exception_handler(AppError)
async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


@app.exception_handler(RequestValidationError)
async def request_validation_handler(
    _: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "INVALID_REQUEST",
                "message": "The request parameters are invalid.",
                "details": exc.errors(),
            }
        },
    )


@app.exception_handler(Exception)
async def unexpected_error_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unexpected request failure")
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "The request could not be completed.",
            }
        },
    )


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def dashboard(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={"app_name": settings.app_name},
    )


@app.get("/results", response_class=HTMLResponse, include_in_schema=False)
def document_result(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="document_result.html",
        context={"app_name": settings.app_name},
    )
