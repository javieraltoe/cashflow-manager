"""Dashboard CashFlow Manager - Sprint 0: verifica conectividad con la API.

Ejecutar local:  streamlit run dashboard/app.py
Los KPIs reales llegan en el Sprint 4.
"""

import os

import httpx
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1").rstrip("/")

st.set_page_config(page_title="CashFlow Manager", page_icon="💵", layout="wide")
st.title("CashFlow Manager · Dashboard")
st.caption("Sprint 0 · verificación de entorno")


@st.cache_data(ttl=5)
def fetch_health() -> tuple[int | None, dict | str]:
    try:
        resp = httpx.get(f"{API_BASE_URL}/health", timeout=3)
        return resp.status_code, resp.json()
    except httpx.HTTPError as exc:
        return None, f"No se pudo conectar con la API: {type(exc).__name__}"


status_code, payload = fetch_health()

col1, col2 = st.columns(2)
if status_code == 200:
    col1.success("API: conectada")
    col2.success("Base de datos: OK")
elif status_code == 503:
    col1.success("API: conectada")
    col2.error("Base de datos: no disponible")
else:
    col1.error("API: sin conexión")
    col2.warning("Base de datos: desconocido")

with st.expander("Detalle técnico"):
    st.write(f"API_BASE_URL = `{API_BASE_URL}`")
    if isinstance(payload, dict):
        st.json(payload)
    else:
        st.code(payload)

if st.button("Reintentar"):
    fetch_health.clear()
    st.rerun()
