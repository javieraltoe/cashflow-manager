"""Dashboard web de CashFlow Manager (spec §4 y §6).

Ejecutar local:  streamlit run dashboard/app.py   (o .\\scripts\\dev.ps1 dashboard)
Solo consume la API (API_BASE_URL); nunca accede a la base de datos.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import streamlit as st  # noqa: E402

from components import charts  # noqa: E402
from components.api import ApiError, DashboardApi, SessionExpired  # noqa: E402
from components.data import (  # noqa: E402
    Filters,
    aging_csv,
    debtor_rows,
    debtors_csv,
    load_dashboard,
    monthly_csv,
    monthly_rows,
    upcoming_csv,
    upcoming_rows,
)
from components.fmt import default_period, fdate, money, pct, today_local  # noqa: E402

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1").rstrip("/")
ROLE_LABELS = {"admin": "Administrador", "operator": "Operador"}

st.set_page_config(page_title="CashFlow Manager · Dashboard", page_icon="💵", layout="wide")


def get_api() -> DashboardApi:
    if "api" not in st.session_state:
        st.session_state["api"] = DashboardApi(API_BASE_URL)
    return st.session_state["api"]


def logout() -> None:
    get_api().logout()
    st.session_state.pop("api", None)
    st.session_state.pop("clients", None)


def render_login(api: DashboardApi) -> bool:
    """Formulario de ingreso. Devuelve True si el usuario quedó autenticado."""
    box = st.empty()
    with box.container():
        st.title("CashFlow Manager")
        st.caption("Dashboard de cobranzas · ingresá con tu usuario de la aplicación")
        col, _ = st.columns([1, 2])
        with col:
            email = st.text_input("Email", key="login_email")
            password = st.text_input("Contraseña", type="password", key="login_password")
            if not st.button("Ingresar", key="login_button", type="primary"):
                return False
            if not email or not password:
                st.error("Ingresá email y contraseña.")
                return False
            try:
                api.login(email, password)
            except ApiError as exc:
                st.error(exc.message)
                return False
    box.empty()
    return True


def client_options(api: DashboardApi) -> dict[str, str | None]:
    if "clients" not in st.session_state:
        st.session_state["clients"] = api.all_clients()
    options: dict[str, str | None] = {"Todos los clientes": None}
    for c in st.session_state["clients"]:
        label = c["name"] if c["is_active"] else f"{c['name']} (inactivo)"
        options[label] = c["id"]
    return options


def render_filters(api: DashboardApi) -> Filters | None:
    today = today_local()
    with st.sidebar:
        user = api.user or {}
        st.markdown(f"**{user.get('full_name', '')}**  \n{ROLE_LABELS.get(user.get('role'), '')}")
        st.button("Cerrar sesión", key="logout_button", on_click=logout)
        st.divider()
        st.subheader("Filtros")
        start, end = default_period(today)
        period = st.date_input(
            "Período (cobranzas)",
            value=(start, end),
            max_value=today,
            format="DD/MM/YYYY",
            key="period",
        )
        options = client_options(api)
        client_label = st.selectbox("Cliente", list(options), key="client")
        days = st.selectbox(
            "Próximos vencimientos", [7, 15, 30, 60], format_func=lambda d: f"{d} días", key="days"
        )
    if not isinstance(period, tuple | list) or len(period) != 2:
        st.info("Elegí la fecha de fin del período en el calendario.")
        return None
    return Filters(
        date_from=period[0],
        date_to=period[1],
        client_id=options.get(client_label),
        upcoming_days=days,
    )


def render_dashboard(api: DashboardApi, f: Filters) -> None:
    data = load_dashboard(api, f)
    o = data.overview
    st.title("Cobranzas")
    st.caption(
        f"Indicadores **a hoy** ({fdate(o['as_of'])}): no cambian con el período. "
        f"Indicadores **del período** ({fdate(f.date_from)} al {fdate(f.date_to)}): "
        "cobrado y serie mensual."
    )

    st.markdown("##### A hoy")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Saldo total por cobrar", money(o["total_receivable"], decimals=False))
    c2.metric(
        "Saldo vencido",
        money(o["overdue_balance"], decimals=False),
        help="Saldo de facturas con vencimiento anterior a hoy",
    )
    c3.metric("% vencido", pct(o["overdue_pct"]))
    c4.metric("Facturas vencidas", f"{o['overdue_count']:,}".replace(",", "."))
    c5, c6, _c7, _c8 = st.columns(4)
    c5.metric(
        f"Vence en {o['due_soon_days']} días",
        money(o["due_soon_balance"], decimals=False),
        help=f"{o['due_soon_count']} facturas no vencidas que vencen entre hoy y hoy + 7",
    )
    c6.metric(
        "Saldo a favor disponible",
        money(o["credit_available"], decimals=False),
        help="Dinero recibido de clientes que todavía no se imputó a facturas",
    )

    st.markdown("##### Del período")
    p1, p2, p3, _p4 = st.columns(4)
    p1.metric("Cobrado", money(o["collected"], decimals=False))
    p2.metric("Pagos imputados", money(o["collected_payments"], decimals=False))
    p3.metric("Saldo a favor recibido", money(o["collected_credits"], decimals=False))

    if data.is_empty:
        st.info("Todavía no hay facturas ni cobros para mostrar con estos filtros.")
        return

    st.divider()
    left, right = st.columns(2)
    with left:
        st.subheader("Cobranza mensual")
        st.plotly_chart(charts.monthly_figure(data.monthly["items"]), use_container_width=True)
        with st.expander("Ver tabla"):
            st.dataframe(monthly_rows(data), hide_index=True, use_container_width=True)
        st.download_button(
            "Exportar CSV", monthly_csv(data), "cobranza_mensual.csv", "text/csv", key="dl_monthly"
        )
    with right:
        st.subheader("Vencido por antigüedad")
        st.plotly_chart(charts.aging_figure(data.aging["items"]), use_container_width=True)
        with st.expander("Ver tabla"):
            st.dataframe(
                [
                    {"Días": b["bucket"], "Vencido": money(b["balance"]), "Facturas": b["count"]}
                    for b in data.aging["items"]
                ],
                hide_index=True,
                use_container_width=True,
            )
        st.download_button(
            "Exportar CSV", aging_csv(data), "vencido_por_antiguedad.csv", "text/csv",
            key="dl_aging",
        )  # fmt: skip

    st.divider()
    left, right = st.columns(2)
    with left:
        st.subheader("Principales deudores")
        if data.debtors["items"]:
            st.plotly_chart(charts.debtors_figure(data.debtors["items"]), use_container_width=True)
            st.dataframe(debtor_rows(data), hide_index=True, use_container_width=True)
            st.download_button(
                "Exportar CSV", debtors_csv(data), "principales_deudores.csv", "text/csv",
                key="dl_debtors",
            )  # fmt: skip
        else:
            st.info("No hay clientes con saldo pendiente.")
    with right:
        up = data.upcoming
        st.subheader(f"Próximos vencimientos ({up['days']} días)")
        st.caption(f"{up['count']} facturas · {money(up['total_balance'])}")
        if up["items"]:
            st.dataframe(upcoming_rows(data), hide_index=True, use_container_width=True)
            st.download_button(
                "Exportar CSV", upcoming_csv(data), "proximos_vencimientos.csv", "text/csv",
                key="dl_upcoming",
            )  # fmt: skip
        else:
            st.info("No hay vencimientos en ese plazo.")


def main() -> None:
    api = get_api()
    if not api.is_authenticated and not render_login(api):
        return
    try:
        filters = render_filters(api)
        if filters is not None:
            render_dashboard(api, filters)
    except SessionExpired:
        logout()
        st.warning("Tu sesión venció. Volvé a ingresar.")
        render_login(get_api())
    except ApiError as exc:
        st.error(exc.message)


main()
