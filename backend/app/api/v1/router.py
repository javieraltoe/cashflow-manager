"""Router agregador de la API v1. Cada sprint suma sus routers acá."""

from fastapi import APIRouter

from app.api.v1 import auth, clients, credits, health, invoices, me, payments, users

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(me.router)
api_router.include_router(users.router)
api_router.include_router(clients.router)
api_router.include_router(invoices.router)
api_router.include_router(payments.router)
api_router.include_router(credits.router)
