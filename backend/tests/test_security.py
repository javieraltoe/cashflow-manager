"""Tests unitarios de contraseñas, tokens y limitador de login."""

import uuid
from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import get_settings
from app.core.rate_limit import LoginRateLimiter
from app.core.security import (
    JWT_ALGORITHM,
    create_access_token,
    decode_access_token,
    hash_password,
    hash_refresh_token,
    new_refresh_token,
    verify_password,
)


def test_hash_es_argon2id_y_verifica():
    h = hash_password("una-clave-segura")
    assert h.startswith("$argon2id$")
    assert "una-clave-segura" not in h
    assert verify_password("una-clave-segura", h)
    assert not verify_password("otra-clave", h)


def test_verify_sin_hash_devuelve_false():
    assert not verify_password("lo-que-sea", None)
    assert not verify_password("lo-que-sea", "hash-corrupto")


def test_access_token_ida_y_vuelta():
    uid = uuid.uuid4()
    token, ttl = create_access_token(uid, "admin")
    assert ttl == get_settings().access_token_minutes * 60
    payload = decode_access_token(token)
    assert payload["sub"] == str(uid)
    assert payload["role"] == "admin"


def test_token_vencido_se_rechaza():
    past = datetime.now(UTC) - timedelta(minutes=5)
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "type": "access", "exp": past},
        get_settings().secret_key,
        algorithm=JWT_ALGORITHM,
    )
    assert decode_access_token(token) is None


def test_token_firmado_con_otra_clave_se_rechaza():
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "type": "access", "exp": datetime.now(UTC) + timedelta(1)},
        "otra-clave-cualquiera-de-32-caracteres",
        algorithm=JWT_ALGORITHM,
    )
    assert decode_access_token(token) is None


def test_token_de_otro_tipo_se_rechaza():
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "type": "refresh", "exp": datetime.now(UTC) + timedelta(1)},
        get_settings().secret_key,
        algorithm=JWT_ALGORITHM,
    )
    assert decode_access_token(token) is None


def test_algoritmo_none_se_rechaza():
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "type": "access", "exp": datetime.now(UTC) + timedelta(1)},
        key=None,
        algorithm="none",
    )
    assert decode_access_token(token) is None


def test_refresh_token_solo_se_guarda_hasheado():
    raw, digest = new_refresh_token()
    assert len(raw) >= 40
    assert digest == hash_refresh_token(raw)
    assert raw not in digest


def test_limitador_bloquea_y_se_resetea():
    lim = LoginRateLimiter(max_attempts=3, window_seconds=60)
    for _ in range(3):
        assert not lim.is_blocked("a@b.com")
        lim.register_failure("a@b.com")
    assert lim.is_blocked("a@b.com")
    assert not lim.is_blocked("otro@b.com")
    lim.reset("a@b.com")
    assert not lim.is_blocked("a@b.com")


def test_limitador_olvida_fallos_viejos():
    ahora = [1000.0]
    lim = LoginRateLimiter(max_attempts=1, window_seconds=60, clock=lambda: ahora[0])
    lim.register_failure("x")
    assert lim.is_blocked("x")
    ahora[0] += 61
    assert not lim.is_blocked("x")
