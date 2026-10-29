"""Cliente HTTP de la API v1 para el escritorio (sin dependencias de Qt).

- Sesión: access token corto + refresh token rotatorio, ambos SOLO en memoria (no se
  guardan en disco). Si el access vence, se renueva una vez de forma transparente; si el
  refresh también venció, se lanza SessionExpired y la interfaz vuelve al login.
- Errores: toda falla se convierte en ApiError(status, code, message, field) con el
  mensaje en español que devuelve la API, o uno propio si no hay conexión.
- Montos: se envían como string ("1234.50") y se reciben como string; nunca float.
- Idempotencia: los cobros llevan Idempotency-Key; quien llama genera la clave una vez por
  operación y la reutiliza si reintenta (doble clic, corte de red).
"""

import contextlib
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

import httpx

from desktop.app import __version__

DEFAULT_TIMEOUT = 15.0
MAX_PAGE_SIZE = 100


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, field: str | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.field = field

    def __repr__(self) -> str:  # pragma: no cover - ayuda de depuración
        return f"ApiError({self.status}, {self.code!r}, {self.message!r}, field={self.field!r})"


class SessionExpired(ApiError):
    """La sesión no se pudo renovar: hay que volver a ingresar."""


@dataclass
class Created:
    """Resultado de un alta idempotente: `replayed=True` si el servidor ya la tenía."""

    data: dict
    replayed: bool


def new_idempotency_key() -> str:
    return str(uuid.uuid4())


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(v) for v in value]
    return value


def _clean_params(params: dict[str, Any] | None) -> dict[str, Any]:
    return {k: _jsonable(v) for k, v in (params or {}).items() if v is not None and v != ""}


class ApiClient:
    def __init__(
        self,
        base_url: str,
        http: httpx.Client | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._http = http or httpx.Client(
            timeout=timeout,
            headers={"User-Agent": f"CashFlowManager-Desktop/{__version__}"},
        )
        self._access: str | None = None
        self._refresh: str | None = None
        self.user: dict | None = None

    # ---------- Sesión ----------

    @property
    def is_authenticated(self) -> bool:
        return self._access is not None

    @property
    def is_admin(self) -> bool:
        return bool(self.user and self.user.get("role") == "admin")

    def login(self, email: str, password: str) -> dict:
        tokens = self._send(
            "POST", "/auth/login", json={"email": email.strip(), "password": password}, auth=False
        )
        self._store_tokens(tokens)
        self.user = self.me()
        return self.user

    def logout(self) -> None:
        refresh, self._refresh = self._refresh, None
        self._access, self.user = None, None
        if refresh:
            # Cerrar sesión localmente siempre funciona, aunque el servidor no responda.
            with contextlib.suppress(ApiError):
                self._send("POST", "/auth/logout", json={"refresh_token": refresh}, auth=False)

    def close(self) -> None:
        self._http.close()

    def _store_tokens(self, tokens: dict) -> None:
        self._access = tokens["access_token"]
        self._refresh = tokens["refresh_token"]

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
        self._store_tokens(tokens)
        return True

    # ---------- Transporte ----------

    def _send(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        auth: bool = True,
        raw: bool = False,
        files: dict[str, tuple[str, bytes, str]] | None = None,
        data: dict[str, str] | None = None,
        _retried: bool = False,
    ) -> Any:
        hdrs = dict(headers or {})
        if auth:
            if not self._access:
                raise SessionExpired(401, "unauthorized", "Iniciá sesión para continuar")
            hdrs["Authorization"] = f"Bearer {self._access}"
        try:
            resp = self._http.request(
                method,
                f"{self.base_url}{path}",
                json=_jsonable(json) if json is not None else None,
                params=_clean_params(params),
                headers=hdrs,
                files=files,
                data=data,
            )
        except httpx.TimeoutException as exc:
            raise ApiError(
                0, "timeout", "El servidor tardó demasiado en responder. Probá de nuevo."
            ) from exc
        except httpx.TransportError as exc:
            raise ApiError(
                0,
                "network_error",
                "No se pudo conectar con el servidor. Revisá la conexión y la dirección "
                "configurada.",
            ) from exc

        if resp.status_code == 401 and auth:
            if not _retried and self._try_refresh():
                return self._send(
                    method,
                    path,
                    json=json,
                    params=params,
                    headers=headers,
                    auth=auth,
                    raw=raw,
                    files=files,
                    data=data,
                    _retried=True,
                )
            self.user = None
            raise SessionExpired(401, "session_expired", "Tu sesión venció. Volvé a ingresar.")
        if resp.status_code >= 400:
            raise self._error_from(resp)
        if raw:
            return resp
        return resp.json() if resp.content else None

    @staticmethod
    def _error_from(resp: httpx.Response) -> ApiError:
        try:
            err = resp.json()["error"]
            return ApiError(resp.status_code, err["code"], err["message"], err.get("field"))
        except (ValueError, KeyError, TypeError):
            return ApiError(
                resp.status_code,
                "http_error",
                f"El servidor respondió con un error inesperado (HTTP {resp.status_code}).",
            )

    def _create(self, path: str, data: dict, idempotency_key: str) -> Created:
        resp = self._send(
            "POST", path, json=data, headers={"Idempotency-Key": idempotency_key}, raw=True
        )
        return Created(resp.json(), resp.headers.get("Idempotent-Replayed") == "true")

    # ---------- Endpoints ----------

    def health(self) -> dict:
        resp = self._http.get(f"{self.base_url}/health")
        return resp.json()

    def me(self) -> dict:
        return self._send("GET", "/me")

    def change_password(self, current: str, new: str) -> None:
        self._send("POST", "/me/password", json={"current_password": current, "new_password": new})
        # El servidor revoca todas las sesiones: el refresh actual ya no sirve.
        self._refresh = None

    # Usuarios (admin)
    def list_users(self, page: int = 1, page_size: int = MAX_PAGE_SIZE) -> dict:
        return self._send("GET", "/users", params={"page": page, "page_size": page_size})

    def create_user(self, data: dict) -> dict:
        return self._send("POST", "/users", json=data)

    def update_user(self, user_id: str, data: dict) -> dict:
        return self._send("PATCH", f"/users/{user_id}", json=data)

    # Clientes
    def list_clients(self, **params: Any) -> dict:
        return self._send("GET", "/clients", params=params)

    def all_clients(self, is_active: bool | None = True, max_pages: int = 50) -> list[dict]:
        """Todos los clientes (para combos). Corta en max_pages × 100 por seguridad."""
        items: list[dict] = []
        for page in range(1, max_pages + 1):
            data = self.list_clients(is_active=is_active, page=page, page_size=MAX_PAGE_SIZE)
            items.extend(data["items"])
            if len(items) >= data["total"] or not data["items"]:
                break
        return items

    def get_client(self, client_id: str) -> dict:
        return self._send("GET", f"/clients/{client_id}")

    def create_client(self, data: dict) -> dict:
        return self._send("POST", "/clients", json=data)

    def update_client(self, client_id: str, data: dict) -> dict:
        return self._send("PATCH", f"/clients/{client_id}", json=data)

    # Facturas
    def list_invoices(self, **params: Any) -> dict:
        return self._send("GET", "/invoices", params=params)

    def get_invoice(self, invoice_id: str) -> dict:
        return self._send("GET", f"/invoices/{invoice_id}")

    def create_invoice(self, data: dict) -> dict:
        return self._send("POST", "/invoices", json=data)

    def update_invoice(self, invoice_id: str, data: dict) -> dict:
        return self._send("PATCH", f"/invoices/{invoice_id}", json=data)

    def void_invoice(self, invoice_id: str) -> dict:
        return self.update_invoice(invoice_id, {"is_void": True})

    # Pagos
    def list_payments(self, **params: Any) -> dict:
        return self._send("GET", "/payments", params=params)

    def create_payment(self, data: dict, idempotency_key: str) -> Created:
        return self._create("/payments", data, idempotency_key)

    def void_payment(self, payment_id: str, reason: str) -> dict:
        return self._send("POST", f"/payments/{payment_id}/void", json={"reason": reason})

    # Indicadores (los mismos que usa el dashboard web)
    def metrics_overview(self, **params: Any) -> dict:
        return self._send("GET", "/metrics/overview", params=params)

    def metrics_upcoming(self, **params: Any) -> dict:
        return self._send("GET", "/metrics/upcoming", params=params)

    # Importación y exportación CSV
    def _import(self, step: str, content: bytes, filename: str, create_missing: bool) -> dict:
        return self._send(
            "POST",
            f"/imports/invoices/{step}",
            files={"file": (filename, content, "text/csv")},
            data={"create_missing_clients": "true" if create_missing else "false"},
        )

    def preview_import(self, content: bytes, filename: str, create_missing: bool = False) -> dict:
        return self._import("preview", content, filename, create_missing)

    def commit_import(self, content: bytes, filename: str, create_missing: bool = False) -> dict:
        return self._import("commit", content, filename, create_missing)

    def export_invoices(self, **params: Any) -> bytes:
        """CSV de facturas con los mismos filtros que list_invoices."""
        return self._send("GET", "/exports/invoices.csv", params=params, raw=True).content

    # Saldo a favor
    def client_credit(self, client_id: str) -> dict:
        return self._send("GET", f"/clients/{client_id}/credit")

    def list_credits(self, **params: Any) -> dict:
        return self._send("GET", "/credits", params=params)

    def create_credit(self, data: dict, idempotency_key: str) -> Created:
        return self._create("/credits", data, idempotency_key)

    def apply_credit(self, invoice_id: str, amount: Decimal, idempotency_key: str) -> Created:
        return self._create(
            "/credits/apply", {"invoice_id": invoice_id, "amount": amount}, idempotency_key
        )

    def void_credit(self, credit_id: str, reason: str) -> dict:
        return self._send("POST", f"/credits/{credit_id}/void", json={"reason": reason})
