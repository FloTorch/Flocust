"""FastAPI application entry point for Flocust LLM load testing API."""

from fastapi import FastAPI

from flocust.api.constants import (
    API_PREFIX,
    API_VERSION,
    DOCS_PATH,
    OPENAPI_JSON_PATH,
    SERVICE_NAME,
)
from flocust.api.routes import router

app = FastAPI(
    title=SERVICE_NAME,
    description="LLM endpoint load testing with Locust: benchmark latency, TTFT, and inter-token latency.",
    version=API_VERSION,
    docs_url=DOCS_PATH,
    openapi_url=OPENAPI_JSON_PATH,
)

app.include_router(router)


@app.get("/", summary="Health and API info")
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
