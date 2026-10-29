"""Clientes: listado con búsqueda, alta, edición y activación/desactivación (HU02)."""

from PySide6.QtWidgets import QLineEdit, QPushButton, QWidget

from desktop.app.views.base import AppContext, BasePage, FormDialog
from desktop.app.widgets import messages
from desktop.app.widgets.common import ChoiceCombo, FieldError, Pager
from desktop.app.widgets.table import Column, DataTable, field

PAGE_SIZE = 50


class ClientDialog(FormDialog):
    def __init__(self, ctx: AppContext, client: dict | None = None, parent: QWidget | None = None):
        super().__init__(ctx, "Editar cliente" if client else "Nuevo cliente", parent)
        self.client = client
        self.name = QLineEdit((client or {}).get("name", ""))
        self.tax_id = QLineEdit((client or {}).get("tax_id") or "")
        self.tax_id.setPlaceholderText("30-12345678-9")
        self.email = QLineEdit((client or {}).get("email") or "")
        self.phone = QLineEdit((client or {}).get("phone") or "")
        self.add_row("Nombre / Razón social *", self.name, "name")
        self.add_row("CUIT", self.tax_id, "tax_id")
        self.add_row("Email", self.email, "email")
        self.add_row("Teléfono", self.phone, "phone")

    def submit(self):
        data = {
            "name": self.name.text().strip(),
            "tax_id": self.tax_id.text().strip() or None,
            "email": self.email.text().strip() or None,
            "phone": self.phone.text().strip() or None,
        }
        if not data["name"]:
            raise FieldError("name", "El nombre es obligatorio")
        if self.client:
            changes = {k: v for k, v in data.items() if v != self.client.get(k)}
            if not changes:
                return self.client
            result = self.ctx.api.update_client(self.client["id"], changes)
        else:
            result = self.ctx.api.create_client(data)
        self.ctx.invalidate_clients()
        return result


class ClientsPage(BasePage):
    title = "Clientes"

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(ctx, parent)
        bar = self.toolbar()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar por nombre, CUIT o email…")
        self.search.returnPressed.connect(self.search_now)
        self.state = ChoiceCombo([("Activos", True), ("Inactivos", False), ("Todos", None)])
        self.state.currentIndexChanged.connect(self.search_now)
        search_btn = QPushButton("Buscar")
        search_btn.clicked.connect(self.search_now)
        bar.addWidget(self.search, 1)
        bar.addWidget(self.state)
        bar.addWidget(search_btn)

        self.table = DataTable(
            [
                Column("Nombre", field("name")),
                Column("CUIT", field("tax_id")),
                Column("Email", field("email")),
                Column("Teléfono", field("phone")),
                Column("Estado", lambda c: "Activo" if c["is_active"] else "Inactivo"),
            ]
        )
        self.table.doubleClicked.connect(self.edit_selected)
        self.layout_.addWidget(self.table, 1)
        self.pager = Pager(PAGE_SIZE)
        self.pager.changed.connect(lambda _p: self.refresh())
        self.layout_.addWidget(self.pager)

        actions = self.toolbar()
        self.new_btn = QPushButton("Nuevo cliente")
        self.edit_btn = QPushButton("Editar")
        self.toggle_btn = QPushButton("Desactivar / Activar")
        self.new_btn.clicked.connect(self.create)
        self.edit_btn.clicked.connect(self.edit_selected)
        self.toggle_btn.clicked.connect(self.toggle_selected)
        for b in (self.new_btn, self.edit_btn, self.toggle_btn):
            actions.addWidget(b)
        actions.addStretch(1)

    def search_now(self) -> None:
        self.pager.reset()
        self.refresh()

    def refresh(self) -> None:
        page = self.ctx.call(
            self,
            self.ctx.api.list_clients,
            q=self.search.text().strip() or None,
            is_active=self.state.value(),
            page=self.pager.page,
            page_size=PAGE_SIZE,
        )
        if page is None:
            return
        self.table.set_rows(page["items"])
        self.pager.update_total(page["total"])

    def create(self) -> None:
        dlg = ClientDialog(self.ctx, parent=self)
        if dlg.exec():
            self.refresh()

    def edit_selected(self) -> None:
        client = self.table.selected()
        if client is None:
            messages.show_info(self, "Seleccioná un cliente de la lista.")
            return
        dlg = ClientDialog(self.ctx, client, parent=self)
        if dlg.exec():
            self.refresh()

    def toggle_selected(self) -> None:
        client = self.table.selected()
        if client is None:
            messages.show_info(self, "Seleccioná un cliente de la lista.")
            return
        activate = not client["is_active"]
        verb = "activar" if activate else "desactivar"
        extra = "" if activate else "\nNo se le podrán cargar facturas nuevas."
        if not messages.ask_yes_no(self, f"¿Querés {verb} a {client['name']}?{extra}"):
            return
        if self.ctx.call(self, self.ctx.api.update_client, client["id"], {"is_active": activate}):
            self.ctx.invalidate_clients()
            self.refresh()
