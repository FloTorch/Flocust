"""FastAPI application entry point for Flocust LLM load testing API."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from flocust.api.constants import (
    API_VERSION,
    DOCS_PATH,
    OPENAPI_JSON_PATH,
    SERVICE_NAME,
)
from flocust.api.routes import router

logger = logging.getLogger(__name__)

app = FastAPI(
    title=SERVICE_NAME,
    description="LLM endpoint load testing with Locust: benchmark latency, TTFT, and inter-token latency.",
    version=API_VERSION,
    docs_url=DOCS_PATH,
    openapi_url=OPENAPI_JSON_PATH,
)

app.include_router(router)


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Return 422 with validation errors for invalid request body/form."""
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "message": "Request validation failed"},
    )


@app.exception_handler(ValidationError)
async def pydantic_validation_exception_handler(
    request: Request, exc: ValidationError
) -> JSONResponse:
    """Return 422 when Pydantic model validation fails (e.g. RunConfig)."""
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "message": "Validation failed"},
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return 500 with a safe message; log the real exception server-side."""
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "message": "An unexpected error occurred. Please try again.",
        },
    )


@app.get("/health", summary="Health check")
def health() -> dict:
    """Health check for load balancers and monitoring. Returns 200 when the service is up."""
    return {"status": "ok"}


@app.get("/", summary="API info")
def root() -> dict:
    """
    Return service name and links to OpenAPI docs.

    Use this to verify the API is running and to discover docs and OpenAPI JSON URLs.
    """
    return {
        "service": SERVICE_NAME,
        "docs": DOCS_PATH,
        "openapi": OPENAPI_JSON_PATH,
    }
