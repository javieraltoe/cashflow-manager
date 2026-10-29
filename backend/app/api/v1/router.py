"""Router agregador de la API v1. Cada sprint suma sus routers acá."""

from fastapi import APIRouter

from app.api.v1 import health

api_router = APIRouter()
api_router.include_router(health.router)
