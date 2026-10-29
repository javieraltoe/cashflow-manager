"""Importación CSV (spec §4 y §10, HU07): elegir archivo, previsualizar, ver errores,
confirmar. Nada se guarda hasta confirmar."""

from pathlib import Path

from PySide6.QtWidgets import QCheckBox, QLabel, QPushButton, QWidget

from desktop.app.views.base import AppContext, BasePage
from desktop.app.widgets import files, messages
from desktop.app.widgets.table import Column, DataTable, field

MAX_BYTES = 5 * 1024 * 1024
TEMPLATE = (
    "client_name,invoice_number,issue_date,due_date,amount,description\r\n"
    "ACME SA,F-0001,2026-10-01,2026-10-30,125000.50,Servicio mensual\r\n"
)


def row_status(row: dict) -> str:
    if row["status"] == "ok":
        return "Cliente nuevo" if row.get("new_client") else "OK"
    return " · ".join(e["message"] for e in row["errors"])


class ImportPage(BasePage):
    title = "Importar facturas (CSV)"

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(ctx, parent)
        self.path: Path | None = None
        self.content: bytes | None = None
        self.preview: dict | None = None

        help_ = QLabel(
            "Columnas: client_name, invoice_number, issue_date, due_date, amount, description. "
            "Fechas AAAA-MM-DD, importe con punto decimal, UTF-8. Máximo 5 MB y 5.000 filas."
        )
        help_.setWordWrap(True)
        help_.setStyleSheet("color: #57606a;")
        self.layout_.addWidget(help_)

        bar = self.toolbar()
        self.choose_btn = QPushButton("Elegir archivo…")
        self.template_btn = QPushButton("Descargar plantilla")
        self.file_label = QLabel("Ningún archivo elegido")
        self.create_missing = QCheckBox("Crear los clientes que no existan")
        self.preview_btn = QPushButton("Previsualizar")
        self.choose_btn.clicked.connect(self.choose_file)
        self.template_btn.clicked.connect(self.save_template)
        self.preview_btn.clicked.connect(self.run_preview)
        self.create_missing.toggled.connect(lambda _c: self._invalidate())
        for w in (self.choose_btn, self.file_label, self.create_missing, self.preview_btn):
            bar.addWidget(w)
        bar.addStretch(1)
        bar.addWidget(self.template_btn)

        self.summary = QLabel()
        self.summary.setStyleSheet("font-weight: 600; margin: 6px 0;")
        self.layout_.addWidget(self.summary)
        self.table = DataTable(
            [
                Column("Línea", field("line"), align_right=True),
                Column("Cliente", field("client_name")),
                Column("Número", field("invoice_number")),
                Column("Emisión", field("issue_date")),
                Column("Vencimiento", field("due_date")),
                Column("Importe", field("amount"), align_right=True),
                Column(
                    "Resultado",
                    row_status,
                    color=lambda r: "#cf222e" if r["status"] == "error" else "#1a7f37",
                ),
            ]
        )
        self.layout_.addWidget(self.table, 1)

        actions = self.toolbar()
        self.commit_btn = QPushButton("Importar filas válidas")
        self.commit_btn.setEnabled(False)
        self.commit_btn.clicked.connect(self.run_commit)
        actions.addStretch(1)
        actions.addWidget(self.commit_btn)
        self._invalidate()

    def refresh(self) -> None:  # nada que recargar desde el servidor
        pass

    def _invalidate(self) -> None:
        self.preview = None
        self.commit_btn.setEnabled(False)
        self.commit_btn.setText("Importar filas válidas")
        self.table.set_rows([])
        self.summary.setText("Elegí un archivo y previsualizalo antes de importar.")

    def choose_file(self) -> None:
        chosen = files.ask_open_csv(self)
        if not chosen:
            return
        path = Path(chosen)
        try:
            size = path.stat().st_size
            if size > MAX_BYTES:
                messages.show_error(self, "El archivo supera el máximo de 5 MB.")
                return
            self.content = path.read_bytes()
        except OSError as exc:
            messages.show_error(self, f"No se pudo leer el archivo: {exc.strerror or exc}")
            return
        self.path = path
        self.file_label.setText(path.name)
        self._invalidate()
        self.run_preview()

    def run_preview(self) -> None:
        if self.content is None or self.path is None:
            messages.show_info(self, "Primero elegí un archivo CSV.")
            return
        self._invalidate()
        result = self.ctx.call(
            self,
            self.ctx.api.preview_import,
            self.content,
            self.path.name,
            self.create_missing.isChecked(),
        )
        if result is None:
            return
        self.preview = result
        self.table.set_rows(result["rows"])
        new = f" · {len(result['new_clients'])} clientes nuevos" if result["new_clients"] else ""
        self.summary.setText(
            f"{result['row_count']} filas · {result['valid_count']} válidas · "
            f"{result['rejected_count']} con errores{new}"
        )
        self.commit_btn.setEnabled(result["valid_count"] > 0)
        self.commit_btn.setText(f"Importar {result['valid_count']} facturas válidas")

    def run_commit(self) -> None:
        if not self.preview or self.content is None or self.path is None:
            return
        p = self.preview
        text = f"Se van a cargar {p['valid_count']} facturas"
        if p["new_clients"]:
            text += f" y crear {len(p['new_clients'])} clientes ({', '.join(p['new_clients'])})"
        if p["rejected_count"]:
            text += f". Las {p['rejected_count']} filas con errores no se importan"
        if not messages.ask_yes_no(self, text + ".\n\n¿Continuar?"):
            return
        result = self.ctx.call(
            self,
            self.ctx.api.commit_import,
            self.content,
            self.path.name,
            self.create_missing.isChecked(),
        )
        if result is None:
            return
        if result["created_clients"]:
            self.ctx.invalidate_clients()
        msg = f"Importación terminada: {result['imported_count']} facturas cargadas"
        if result["rejected_count"]:
            msg += f", {result['rejected_count']} filas rechazadas"
        messages.show_info(self, msg + ".")
        self._invalidate()
        self.table.set_rows(result["rejected"])
        if result["rejected"]:
            self.summary.setText("Filas rechazadas en la importación:")

    def save_template(self) -> None:
        target = files.ask_save_csv(self, "plantilla_facturas.csv")
        if not target:
            return
        try:
            Path(target).write_bytes(TEMPLATE.encode("utf-8"))
        except OSError as exc:
            messages.show_error(self, f"No se pudo guardar: {exc.strerror or exc}")
            return
        messages.show_info(self, f"Plantilla guardada en {target}")
