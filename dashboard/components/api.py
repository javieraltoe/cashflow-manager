"""Cliente de la API para el dashboard (el navegador nunca habla con la base: §8).

Los tokens viven en la sesión de Streamlit del servidor (memoria), no en el navegador.
HTTP_FACTORY permite a los tests inyectar el TestClient de FastAPI.
"""

import contextlib
from collections.abc import Callable
from datetime import date
from typing import Any

import httpx

TIMEOUT = 30.0


def _default_http() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT, headers={"User-Agent": "CashFlowManager-Dashboard"})


HTTP_FACTORY: Callable[[], httpx.Client] = _default_http


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, field: str | None = None) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.field = status, code, message, field


class SessionExpired(ApiError):
    pass


def _params(params: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for key, value in params.items():
        if value is None or value == "":
            continue
        out[key] = value.isoformat() if isinstance(value, date) else value
    return out


class DashboardApi:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self._http = HTTP_FACTORY()
        self._access: str | None = None
        self._refresh: str | None = None
        self.user: dict | None = None

    @property
    def is_authenticated(self) -> bool:
        return self._access is not None

    # ---------- Sesión ----------
    def login(self, email: str, password: str) -> dict:
        tokens = self._send(
            "POST", "/auth/login", json={"email": email.strip(), "password": password}, auth=False
        )
        self._access, self._refresh = tokens["access_token"], tokens["refresh_token"]
        self.user = self._send("GET", "/me")
        return self.user

    def logout(self) -> None:
        refresh, self._refresh, self._access, self.user = self._refresh, None, None, None
        if refresh:
            with contextlib.suppress(ApiError):
                self._send("POST", "/auth/logout", json={"refresh_token": refresh}, auth=False)

    def _try_refresh(self) -> bool:
        if not self._refresh:
            return False
        try:
            tokens = self._send(
                "POST", "/auth/refresh", json={"refresh_token": self._refresh}, auth=False
            )
        except ApiError:
            self._access = self._refresh = None
            return False
        self._access, self._refresh = tokens["access_token"], tokens["refresh_token"]
        return True

    # ---------- Transporte ----------
    def _send(self, method, path, *, json=None, params=None, auth=True, _retried=False):
        headers = {}
        if auth:
            if not self._access:
                raise SessionExpired(401, "unauthorized", "Iniciá sesión para continuar")
            headers["Authorization"] = f"Bearer {self._access}"
        try:
            resp = self._http.request(
                method,
                f"{self.base_url}{path}",
                json=json,
                params=_params(params or {}),
                headers=headers,
            )
        except httpx.TimeoutException as exc:
            raise ApiError(0, "timeout", "La API tardó demasiado en responder.") from exc
        except httpx.TransportError as exc:
            raise ApiError(0, "network_error", "No se pudo conectar con la API.") from exc
        if resp.status_code == 401 and auth:
            if not _retried and self._try_refresh():
                return self._send(method, path, json=json, params=params, auth=auth, _retried=True)
            self.user = None
            self._access = None
            raise SessionExpired(401, "session_expired", "Tu sesión venció. Volvé a ingresar.")
        if resp.status_code >= 400:
            try:
                err = resp.json()["error"]
                raise ApiError(resp.status_code, err["code"], err["message"], err.get("field"))
            except (ValueError, KeyError, TypeError):
                raise ApiError(
                    resp.status_code, "http_error", f"Error inesperado (HTTP {resp.status_code})"
                ) from None
        return resp.json() if resp.content else None

    # ---------- Datos ----------
    def overview(self, **params) -> dict:
        return self._send("GET", "/metrics/overview", params=params)

    def collections_monthly(self, **params) -> dict:
        return self._send("GET", "/metrics/collections-monthly", params=params)

    def aging(self, **params) -> dict:
        return self._send("GET", "/metrics/aging", params=params)

    def top_debtors(self, **params) -> dict:
        return self._send("GET", "/metrics/top-debtors", params=params)

    def upcoming(self, **params) -> dict:
        return self._send("GET", "/metrics/upcoming", params=params)

    def all_clients(self, max_pages: int = 50) -> list[dict]:
        items: list[dict] = []
        for page in range(1, max_pages + 1):
            data = self._send("GET", "/clients", params={"page": page, "page_size": 100})
            items.extend(data["items"])
            if len(items) >= data["total"] or not data["items"]:
                break
        return items
