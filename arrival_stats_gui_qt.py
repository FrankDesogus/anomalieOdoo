"""
GUI desktop PySide6 per la generazione del report statistiche ingressi.

Avvio:  .venv\\Scripts\\python.exe arrival_stats_gui_qt.py

Tutto il calcolo e la persistenza sono in:
  app/stats_builder.py   — motore statistico (non importato direttamente)
  app/stats_report.py    — generazione Excel (non importato direttamente)
  app/stats_service.py   — service layer (fetch + pipeline)
  app/pool_store.py      — pool JSON
  app/report_paths.py    — filename helpers

La GUI non duplica nessuna logica di business.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QDate, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDateEdit,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

import yaml
from datetime import time as _time

from app.odoo_client import OdooClient
from app.pool_store import Pool, delete_pool, list_pools, load_pool, save_pool, validate_pool_name
from app.report_paths import build_default_report_filename, next_available_path
from app.stats_service import (
    ArrivalStatsParams,
    ArrivalStatsResult,
    fetch_sessions,
    resolve_pool_from_ids,
    run_pipeline,
    validate_params,
)

POOLS_DIR = Path("config/pools")
CONFIG_FILE = "config.yaml"

# ---------------------------------------------------------------------------
# Stylesheet
# ---------------------------------------------------------------------------

_STYLESHEET = """
QMainWindow, QScrollArea > QWidget > QWidget {
    background-color: #f2f2f2;
}
QWidget {
    font-family: "Segoe UI";
    font-size: 10pt;
    color: #1a1a1a;
}
QGroupBox {
    font-weight: bold;
    font-size: 10pt;
    border: 1px solid #c8c8c8;
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 10px;
    background-color: #ffffff;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 6px;
    color: #1a1a1a;
}
QPushButton {
    background-color: #e3e3e3;
    border: 1px solid #b0b0b0;
    border-radius: 4px;
    padding: 5px 14px;
    min-height: 26px;
    color: #1a1a1a;
}
QPushButton:hover  { background-color: #d3d3d3; border-color: #909090; }
QPushButton:pressed { background-color: #c0c0c0; }
QPushButton:disabled { background-color: #f0f0f0; color: #a0a0a0; border-color: #d0d0d0; }
QPushButton#btn_generate {
    background-color: #0067b8;
    color: white;
    font-weight: bold;
    font-size: 11pt;
    min-height: 36px;
    padding: 7px 28px;
    border: none;
    border-radius: 5px;
}
QPushButton#btn_generate:hover   { background-color: #005ba1; }
QPushButton#btn_generate:pressed { background-color: #004f8e; }
QPushButton#btn_generate:disabled { background-color: #99bedd; color: #e0e0e0; }
QLineEdit, QSpinBox, QComboBox, QDateEdit, QTimeEdit {
    border: 1px solid #c0c0c0;
    border-radius: 4px;
    padding: 4px 8px;
    background-color: #ffffff;
    min-height: 24px;
    selection-background-color: #0067b8;
    selection-color: white;
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus,
QDateEdit:focus, QTimeEdit:focus {
    border-color: #0067b8;
}
QListWidget {
    border: 1px solid #c0c0c0;
    border-radius: 4px;
    background-color: #ffffff;
    alternate-background-color: #f7f7f7;
    outline: none;
}
QListWidget::item            { padding: 4px 8px; border-bottom: 1px solid #f0f0f0; }
QListWidget::item:hover      { background-color: #e8f1fb; }
QListWidget::item:selected   { background-color: #cce0f5; color: #000000; }
QProgressBar {
    border: 1px solid #c0c0c0;
    border-radius: 4px;
    background-color: #ebebeb;
    text-align: center;
    min-height: 20px;
    color: #333;
    font-size: 9pt;
}
QProgressBar::chunk { background-color: #0067b8; border-radius: 3px; }
QScrollArea         { border: none; background-color: #f2f2f2; }
/* ---- Calendario popup (QDateEdit) --------------------------------- */
QCalendarWidget {
    background-color: #ffffff;
}
QCalendarWidget QWidget {
    background-color: #ffffff;
    color: #1a1a1a;
    alternate-background-color: #f5f5f5;
}
QCalendarWidget #qt_calendar_navigationbar {
    background-color: #e8eef5;
    padding: 4px 2px;
    border-bottom: 1px solid #c8d4e0;
}
QCalendarWidget QToolButton {
    background-color: transparent;
    border: none;
    color: #1a1a1a;
    font-size: 10pt;
    font-weight: bold;
    border-radius: 4px;
    padding: 3px 8px;
    min-width: 28px;
}
QCalendarWidget QToolButton:hover {
    background-color: #d0dff0;
}
QCalendarWidget QToolButton:pressed {
    background-color: #b8cfe8;
}
QCalendarWidget QToolButton::menu-indicator { image: none; }
QCalendarWidget QSpinBox {
    background-color: #ffffff;
    border: 1px solid #c0c0c0;
    border-radius: 3px;
    color: #1a1a1a;
    padding: 2px 4px;
    selection-background-color: #0067b8;
    selection-color: white;
}
QCalendarWidget QAbstractItemView {
    background-color: #ffffff;
    color: #1a1a1a;
    selection-background-color: #0067b8;
    selection-color: #ffffff;
    gridline-color: #f0f0f0;
    outline: none;
}
QCalendarWidget QAbstractItemView:disabled {
    color: #b0b0b0;
}
QCalendarWidget QAbstractItemView::item:hover {
    background-color: #e0eef8;
    color: #1a1a1a;
}
QCalendarWidget QAbstractItemView::item:selected {
    background-color: #0067b8;
    color: #ffffff;
    border-radius: 3px;
}
QCalendarWidget QMenu {
    background-color: #ffffff;
    border: 1px solid #c0c0c0;
    color: #1a1a1a;
}
QCalendarWidget QMenu::item:selected {
    background-color: #0067b8;
    color: white;
}
QStatusBar {
    background-color: #e8e8e8;
    border-top: 1px solid #d0d0d0;
    font-size: 9pt;
    color: #555;
}
QLabel#lbl_preview {
    font-family: "Consolas", "Courier New";
    font-size: 9pt;
    color: #222;
}
QLabel#lbl_result {
    font-family: "Consolas", "Courier New";
    font-size: 9pt;
    background-color: #f8f8f8;
    border: 1px solid #ddd;
    border-radius: 4px;
    padding: 8px 10px;
}
"""


# ---------------------------------------------------------------------------
# Worker threads
# ---------------------------------------------------------------------------

class _OdooInitWorker(QThread):
    finished: Signal = Signal(object, object, list)
    error: Signal = Signal(str)

    def run(self):
        try:
            cfg = yaml.safe_load(open(CONFIG_FILE, "r", encoding="utf-8"))
            o = cfg["odoo"]
            client = OdooClient(o["url"], o["db"], o["user"], o["password"], cfg["timezone"])
            employees = client.fetch_active_employees()
            self.finished.emit(cfg, client, employees)
        except Exception as exc:
            self.error.emit(str(exc))


class _ReportWorker(QThread):
    progress: Signal = Signal(str, int)
    finished: Signal = Signal(object)
    error: Signal = Signal(str)
    permission_error: Signal = Signal()

    def __init__(self, client, params: ArrivalStatsParams, tz_name: str, parent=None):
        super().__init__(parent)
        self._client = client
        self._params = params
        self._tz_name = tz_name

    def run(self):
        try:
            self.progress.emit("Recupero timbrature da Odoo...", 20)
            sessions = fetch_sessions(
                self._client, self._params.from_day, self._params.to_day, self._tz_name
            )
            self.progress.emit("Calcolo statistiche...", 60)
            result = run_pipeline(sessions, self._params)
            self.progress.emit("Report Excel salvato.", 100)
            self.finished.emit(result)
        except PermissionError:
            self.permission_error.emit()
        except Exception as exc:
            self.error.emit(str(exc))


# ---------------------------------------------------------------------------
# Time spinbox — HH:mm, step configurabile
# ---------------------------------------------------------------------------

class _TimeSpinBox(QSpinBox):
    """
    Spinbox che mostra l'orario come HH:mm.
    Valore interno = minuti da mezzanotte (0–1439).
    Freccette e scroll avanzano di `step` minuti alla volta.
    """

    def __init__(self, hour: int = 8, minute: int = 0, step: int = 10, parent=None):
        super().__init__(parent)
        self.setRange(0, 23 * 60 + 59)
        self.setValue(hour * 60 + minute)
        self.setSingleStep(step)
        self.setWrapping(True)
        self.lineEdit().setReadOnly(True)
        self.setMinimumWidth(100)

    def textFromValue(self, value: int) -> str:
        return f"{value // 60:02d}:{value % 60:02d}"

    def valueFromText(self, text: str) -> int:
        try:
            h, m = text.split(":")
            return int(h) * 60 + int(m)
        except Exception:
            return self.value()

    def validate(self, text, pos):
        from PySide6.QtGui import QValidator
        return (QValidator.State.Acceptable, text, pos)

    def get_time(self) -> _time:
        v = self.value()
        return _time(v // 60, v % 60)


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class ArrivalStatsAppQt(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Statistiche Orari di Ingresso")
        self.setMinimumSize(960, 740)
        self.resize(1100, 920)

        # --- stato interno ---
        self._cfg: dict | None = None
        self._client: OdooClient | None = None
        self._all_employees: list[tuple[int, str]] = []
        self._current_pool_name: str | None = None
        self._filename_manually_edited: bool = False
        self._last_output: Path | None = None

        # --- worker threads ---
        self._init_worker: _OdooInitWorker | None = None
        self._report_worker: _ReportWorker | None = None

        # --- timer anteprima ---
        self._preview_timer: QTimer | None = None

        self._build_ui()
        self.setStyleSheet(_STYLESHEET)
        self.statusBar().showMessage("Connessione a Odoo in corso...")
        self._load_odoo_async()

    # ==================================================================
    # Costruzione UI
    # ==================================================================

    def _build_ui(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        root = QVBoxLayout(container)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        root.addWidget(self._build_periodo())
        root.addWidget(self._build_finestra())

        mid = QWidget()
        mid_lay = QHBoxLayout(mid)
        mid_lay.setContentsMargins(0, 0, 0, 0)
        mid_lay.setSpacing(10)
        mid_lay.addWidget(self._build_dipendenti(), stretch=3)
        mid_lay.addWidget(self._build_pool_panel(), stretch=1)
        root.addWidget(mid)

        root.addWidget(self._build_output())
        root.addWidget(self._build_preview())
        root.addLayout(self._build_generate_row())

        self._result_group = self._build_result()
        self._result_group.setVisible(False)
        root.addWidget(self._result_group)

        root.addStretch()
        scroll.setWidget(container)
        self.setCentralWidget(scroll)

    # ------------------------------------------------------------------
    def _build_periodo(self) -> QGroupBox:
        grp = QGroupBox("Periodo di analisi")
        lay = QHBoxLayout(grp)
        lay.setContentsMargins(14, 18, 14, 12)
        lay.setSpacing(8)

        today = QDate.currentDate()
        lay.addWidget(QLabel("Data iniziale:"))
        self._from_date = QDateEdit(QDate(today.year(), 1, 1))
        self._from_date.setDisplayFormat("yyyy-MM-dd")
        self._from_date.setCalendarPopup(True)
        self._from_date.setMinimumWidth(130)
        lay.addWidget(self._from_date)

        lay.addSpacing(20)
        lay.addWidget(QLabel("Data finale:"))
        self._to_date = QDateEdit(today)
        self._to_date.setDisplayFormat("yyyy-MM-dd")
        self._to_date.setCalendarPopup(True)
        self._to_date.setMinimumWidth(130)
        lay.addWidget(self._to_date)

        lay.addSpacing(20)
        btn_reset = QPushButton("Da gennaio a oggi")
        btn_reset.clicked.connect(self._reset_dates)
        lay.addWidget(btn_reset)
        lay.addStretch()

        self._from_date.dateChanged.connect(self._on_period_changed)
        self._to_date.dateChanged.connect(self._on_period_changed)
        return grp

    # ------------------------------------------------------------------
    def _build_finestra(self) -> QGroupBox:
        grp = QGroupBox("Finestra ingressi validi")
        lay = QHBoxLayout(grp)
        lay.setContentsMargins(14, 18, 14, 12)
        lay.setSpacing(8)

        lay.addWidget(QLabel("Ingresso minimo:"))
        self._arrival_start = _TimeSpinBox(8, 0)
        lay.addWidget(self._arrival_start)

        lay.addSpacing(20)
        lay.addWidget(QLabel("Ingresso massimo:"))
        self._arrival_end = _TimeSpinBox(9, 0)
        lay.addWidget(self._arrival_end)

        lay.addSpacing(20)
        lay.addWidget(QLabel("Ampiezza fasce (min):"))
        self._bucket_spin = QSpinBox()
        self._bucket_spin.setRange(1, 60)
        self._bucket_spin.setValue(10)
        self._bucket_spin.setMinimumWidth(80)
        lay.addWidget(self._bucket_spin)
        lay.addStretch()

        self._arrival_start.valueChanged.connect(self._schedule_preview)
        self._arrival_end.valueChanged.connect(self._schedule_preview)
        self._bucket_spin.valueChanged.connect(self._schedule_preview)
        return grp

    def _get_arrival_start(self) -> _time:
        return self._arrival_start.get_time()

    def _get_arrival_end(self) -> _time:
        return self._arrival_end.get_time()

    # ------------------------------------------------------------------
    def _build_dipendenti(self) -> QGroupBox:
        grp = QGroupBox("Selezione dipendenti")
        lay = QVBoxLayout(grp)
        lay.setContentsMargins(14, 18, 14, 12)
        lay.setSpacing(8)

        # Riga ricerca
        srch = QHBoxLayout()
        srch.setSpacing(8)
        srch.addWidget(QLabel("Cerca:"))
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Nome o ID…")
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.textChanged.connect(self._filter_employees)
        srch.addWidget(self._search_edit)
        btn_sel = QPushButton("Seleziona visibili")
        btn_sel.clicked.connect(self._select_visible)
        srch.addWidget(btn_sel)
        btn_des = QPushButton("Deseleziona tutti")
        btn_des.clicked.connect(self._deselect_all)
        srch.addWidget(btn_des)
        lay.addLayout(srch)

        # Lista dipendenti con checkbox
        self._emp_list = QListWidget()
        self._emp_list.setAlternatingRowColors(True)
        self._emp_list.setMinimumHeight(230)
        self._emp_list.setSortingEnabled(False)
        self._emp_list.itemChanged.connect(self._on_item_changed)
        lay.addWidget(self._emp_list)

        # Stato connessione + contatore
        bot = QHBoxLayout()
        self._conn_label = QLabel("Connessione a Odoo in corso…")
        self._conn_label.setStyleSheet("color: #888;")
        bot.addWidget(self._conn_label)
        bot.addStretch()
        self._counter_label = QLabel("Selezionati: 0")
        self._counter_label.setStyleSheet("color: #0067b8; font-weight: bold;")
        bot.addWidget(self._counter_label)
        lay.addLayout(bot)
        return grp

    # ------------------------------------------------------------------
    def _build_pool_panel(self) -> QGroupBox:
        grp = QGroupBox("Pool dipendenti")
        lay = QVBoxLayout(grp)
        lay.setContentsMargins(14, 18, 14, 12)
        lay.setSpacing(8)

        lay.addWidget(QLabel("Pool salvati:"))
        self._pool_combo = QComboBox()
        self._pool_combo.setEditable(False)
        lay.addWidget(self._pool_combo)

        lay.addSpacing(4)
        for label, slot in (
            ("Carica pool",            self._load_pool),
            ("Salva come nuovo pool",  self._save_pool_as),
            ("Aggiorna pool",          self._update_pool),
            ("Elimina pool",           self._delete_pool),
        ):
            btn = QPushButton(label)
            btn.clicked.connect(slot)
            lay.addWidget(btn)

        lay.addStretch()
        self._refresh_pool_combo()
        return grp

    # ------------------------------------------------------------------
    def _build_output(self) -> QGroupBox:
        grp = QGroupBox("Output")
        grid = QGridLayout(grp)
        grid.setContentsMargins(14, 18, 14, 12)
        grid.setSpacing(8)
        grid.setColumnStretch(1, 1)

        grid.addWidget(QLabel("Cartella destinazione:"), 0, 0)
        self._folder_edit = QLineEdit("reports")
        grid.addWidget(self._folder_edit, 0, 1)
        btn_browse = QPushButton("Sfoglia")
        btn_browse.clicked.connect(self._browse_folder)
        grid.addWidget(btn_browse, 0, 2)

        grid.addWidget(QLabel("Nome file:"), 1, 0)
        self._name_edit = QLineEdit()
        self._name_edit.textEdited.connect(self._on_name_manually_edited)
        grid.addWidget(self._name_edit, 1, 1)
        btn_restore = QPushButton("Ripristina nome suggerito")
        btn_restore.clicked.connect(self._restore_suggested_filename)
        grid.addWidget(btn_restore, 1, 2)

        self._update_suggested_filename()
        return grp

    # ------------------------------------------------------------------
    def _build_preview(self) -> QGroupBox:
        grp = QGroupBox("Anteprima parametri")
        lay = QVBoxLayout(grp)
        lay.setContentsMargins(14, 18, 14, 12)

        self._preview_label = QLabel("—")
        self._preview_label.setObjectName("lbl_preview")
        self._preview_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        lay.addWidget(self._preview_label)
        return grp

    # ------------------------------------------------------------------
    def _build_generate_row(self) -> QHBoxLayout:
        lay = QHBoxLayout()
        lay.setSpacing(14)

        self._gen_btn = QPushButton("  Genera report Excel  ")
        self._gen_btn.setObjectName("btn_generate")
        self._gen_btn.setMinimumWidth(210)
        self._gen_btn.clicked.connect(self._generate_report)
        lay.addWidget(self._gen_btn)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setFormat("%p%")
        self._progress_bar.setMinimumWidth(220)
        lay.addWidget(self._progress_bar)

        lay.addStretch()
        return lay

    # ------------------------------------------------------------------
    def _build_result(self) -> QGroupBox:
        grp = QGroupBox("Risultato")
        lay = QVBoxLayout(grp)
        lay.setContentsMargins(14, 18, 14, 12)
        lay.setSpacing(8)

        self._result_label = QLabel("")
        self._result_label.setObjectName("lbl_result")
        self._result_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        lay.addWidget(self._result_label)

        btn_row = QHBoxLayout()
        btn_folder = QPushButton("Apri cartella")
        btn_folder.clicked.connect(self._open_folder)
        btn_row.addWidget(btn_folder)

        btn_file = QPushButton("Apri file Excel")
        btn_file.clicked.connect(self._open_file)
        btn_row.addWidget(btn_file)
        btn_row.addStretch()
        lay.addLayout(btn_row)
        return grp

    # ==================================================================
    # Connessione Odoo
    # ==================================================================

    def _load_odoo_async(self):
        self._init_worker = _OdooInitWorker(self)
        self._init_worker.finished.connect(self._on_odoo_ready)
        self._init_worker.error.connect(self._on_odoo_error)
        self._init_worker.start()

    @Slot(object, object, list)
    def _on_odoo_ready(self, cfg, client, employees: list):
        self._cfg = cfg
        self._client = client
        self._all_employees = employees
        self._populate_employee_list(employees)
        self._conn_label.setText(f"Connesso — {len(employees)} dipendenti attivi")
        self._conn_label.setStyleSheet("color: #007a00; font-weight: bold;")
        self._update_counter()
        self._schedule_preview()
        self.statusBar().showMessage("Pronto.", 5000)

    @Slot(str)
    def _on_odoo_error(self, msg: str):
        self._conn_label.setText(f"Errore connessione: {msg}")
        self._conn_label.setStyleSheet("color: #c00000; font-weight: bold;")
        self.statusBar().showMessage("Connessione Odoo fallita.")
        QMessageBox.critical(
            self,
            "Errore connessione Odoo",
            f"{msg}\n\nVerificare config.yaml (url, db, user, password)."
        )

    # ==================================================================
    # Lista dipendenti
    # ==================================================================

    def _populate_employee_list(self, employees: list[tuple[int, str]]):
        self._emp_list.blockSignals(True)
        self._emp_list.clear()
        for emp_id, name in sorted(employees, key=lambda e: (e[1] or "").lower()):
            item = QListWidgetItem(f"{name}  [{emp_id}]")
            item.setData(Qt.ItemDataRole.UserRole, (emp_id, name))
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self._emp_list.addItem(item)
        self._emp_list.blockSignals(False)

    def _filter_employees(self):
        query = self._search_edit.text().strip().lower()
        for i in range(self._emp_list.count()):
            item = self._emp_list.item(i)
            emp_id, name = item.data(Qt.ItemDataRole.UserRole)
            visible = not query or query in name.lower() or query in str(emp_id)
            item.setHidden(not visible)

    @Slot(QListWidgetItem)
    def _on_item_changed(self, _item: QListWidgetItem):
        # L'utente ha toccato un checkbox → interrompi collegamento al pool
        self._current_pool_name = None
        self._update_counter()
        self._update_suggested_filename()
        self._schedule_preview()

    def _update_counter(self):
        n = self._count_selected()
        self._counter_label.setText(f"Selezionati: {n}")

    def _count_selected(self) -> int:
        return sum(
            1 for i in range(self._emp_list.count())
            if self._emp_list.item(i).checkState() == Qt.CheckState.Checked
        )

    def _get_selected_pool(self) -> list[tuple[int, str]]:
        result = []
        for i in range(self._emp_list.count()):
            item = self._emp_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                emp_id, name = item.data(Qt.ItemDataRole.UserRole)
                result.append((emp_id, name))
        return result

    def _select_visible(self):
        self._emp_list.blockSignals(True)
        for i in range(self._emp_list.count()):
            item = self._emp_list.item(i)
            if not item.isHidden():
                item.setCheckState(Qt.CheckState.Checked)
        self._emp_list.blockSignals(False)
        self._current_pool_name = None
        self._update_counter()
        self._update_suggested_filename()
        self._schedule_preview()

    def _deselect_all(self):
        self._emp_list.blockSignals(True)
        for i in range(self._emp_list.count()):
            self._emp_list.item(i).setCheckState(Qt.CheckState.Unchecked)
        self._emp_list.blockSignals(False)
        self._current_pool_name = None
        self._update_counter()
        self._update_suggested_filename()
        self._schedule_preview()

    # ==================================================================
    # Gestione pool
    # ==================================================================

    def _refresh_pool_combo(self):
        current = self._pool_combo.currentText()
        self._pool_combo.clear()
        pools = list_pools(POOLS_DIR)
        self._pool_combo.addItems(pools)
        if current in pools:
            self._pool_combo.setCurrentText(current)

    def _load_pool(self):
        name = self._pool_combo.currentText()
        if not name:
            QMessageBox.warning(self, "Pool", "Nessun pool selezionato.")
            return
        try:
            pool = load_pool(name, POOLS_DIR)
        except FileNotFoundError as exc:
            QMessageBox.critical(self, "Pool non trovato", str(exc))
            return

        active = {eid: n for eid, n in self._all_employees}
        valid_pool, missing = resolve_pool_from_ids(pool.employee_ids, active)
        valid_ids = {eid for eid, _ in valid_pool}

        self._emp_list.blockSignals(True)
        for i in range(self._emp_list.count()):
            item = self._emp_list.item(i)
            emp_id, _ = item.data(Qt.ItemDataRole.UserRole)
            item.setCheckState(
                Qt.CheckState.Checked if emp_id in valid_ids else Qt.CheckState.Unchecked
            )
        self._emp_list.blockSignals(False)

        self._current_pool_name = name
        self._update_counter()
        self._update_suggested_filename()
        self._schedule_preview()

        if missing:
            QMessageBox.warning(
                self, "ID non più attivi",
                f"Pool '{name}' caricato.\n\n"
                f"I seguenti ID non sono più tra i dipendenti attivi e sono stati ignorati:\n"
                f"{missing}"
            )
        else:
            self.statusBar().showMessage(
                f"Pool '{name}' caricato — {len(valid_pool)} dipendenti.", 4000
            )

    def _save_pool_as(self):
        selected = self._get_selected_pool()
        if not selected:
            QMessageBox.warning(self, "Pool vuoto",
                                "Selezionare almeno un dipendente prima di salvare.")
            return
        name, ok = QInputDialog.getText(
            self, "Nome pool", "Inserire il nome del nuovo pool:"
        )
        if not ok or not name.strip():
            return
        name = name.strip()
        try:
            validate_pool_name(name)
        except ValueError as exc:
            QMessageBox.critical(self, "Nome non valido", str(exc))
            return
        pool = Pool(name=name, employee_ids=[eid for eid, _ in selected])
        save_pool(pool, POOLS_DIR)
        self._refresh_pool_combo()
        self._pool_combo.setCurrentText(name)
        self._current_pool_name = name
        self._update_suggested_filename()
        self.statusBar().showMessage(
            f"Pool '{name}' salvato ({len(selected)} dipendenti).", 4000
        )

    def _update_pool(self):
        name = self._pool_combo.currentText()
        if not name:
            QMessageBox.warning(self, "Pool", "Nessun pool selezionato.")
            return
        selected = self._get_selected_pool()
        if not selected:
            QMessageBox.warning(self, "Pool vuoto",
                                "Selezionare almeno un dipendente prima di aggiornare.")
            return
        reply = QMessageBox.question(
            self, "Aggiorna pool",
            f"Sovrascrivere il pool '{name}' con la selezione attuale?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        pool = Pool(name=name, employee_ids=[eid for eid, _ in selected])
        save_pool(pool, POOLS_DIR)
        self.statusBar().showMessage(
            f"Pool '{name}' aggiornato ({len(selected)} dipendenti).", 4000
        )

    def _delete_pool(self):
        name = self._pool_combo.currentText()
        if not name:
            QMessageBox.warning(self, "Pool", "Nessun pool selezionato.")
            return
        reply = QMessageBox.question(
            self, "Elimina pool",
            f"Eliminare definitivamente il pool '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            delete_pool(name, POOLS_DIR)
        except FileNotFoundError as exc:
            QMessageBox.critical(self, "Errore", str(exc))
            return
        if self._current_pool_name == name:
            self._current_pool_name = None
            self._update_suggested_filename()
        self._refresh_pool_combo()
        self.statusBar().showMessage(f"Pool '{name}' eliminato.", 4000)

    # ==================================================================
    # Nome file suggerito
    # ==================================================================

    @Slot(str)
    def _on_name_manually_edited(self, _text: str):
        self._filename_manually_edited = True

    def _update_suggested_filename(self):
        if self._filename_manually_edited:
            return
        try:
            fd = self._from_date.date().toPython()
            td = self._to_date.date().toPython()
        except Exception:
            return
        new_name = build_default_report_filename(self._current_pool_name, fd, td)
        # blockSignals per evitare di azionare _on_name_manually_edited
        self._name_edit.blockSignals(True)
        self._name_edit.setText(new_name)
        self._name_edit.blockSignals(False)

    def _restore_suggested_filename(self):
        self._filename_manually_edited = False
        self._update_suggested_filename()

    def _on_period_changed(self):
        self._update_suggested_filename()
        self._schedule_preview()

    # ==================================================================
    # Output
    # ==================================================================

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Scegli cartella di destinazione",
            self._folder_edit.text() or "reports"
        )
        if folder:
            self._folder_edit.setText(folder)

    def _current_output_path(self) -> Path:
        return Path(self._folder_edit.text().strip() or "reports") / self._name_edit.text().strip()

    # ==================================================================
    # Anteprima
    # ==================================================================

    def _schedule_preview(self, *_):
        if self._preview_timer is None:
            self._preview_timer = QTimer(self)
            self._preview_timer.setSingleShot(True)
            self._preview_timer.timeout.connect(self._update_preview)
        self._preview_timer.start(250)

    def _update_preview(self):
        n = self._count_selected()
        out = self._current_output_path()
        try:
            fd = self._from_date.date().toPython()
            td = self._to_date.date().toPython()
            t_start = self._get_arrival_start()
            t_end = self._get_arrival_end()
            bm = self._bucket_spin.value()
            validate_params(fd, td, t_start, t_end, bm)
            self._preview_label.setText(
                f"Dipendenti selezionati : {n}\n"
                f"Periodo                : {fd}  →  {td}\n"
                f"Finestra valida        : {t_start.strftime('%H:%M')}  →  {t_end.strftime('%H:%M')}\n"
                f"Fasce statistiche      : {bm} minuti\n"
                f"Output                 : {out}"
            )
            self._preview_label.setStyleSheet("")
        except Exception as exc:
            self._preview_label.setText(f"Attenzione: {exc}")
            self._preview_label.setStyleSheet("color: #c00000;")

    # ==================================================================
    # Generazione report
    # ==================================================================

    def _generate_report(self):
        if self._cfg is None:
            QMessageBox.critical(
                self, "Odoo non connesso",
                "Attendere il completamento della connessione a Odoo."
            )
            return

        # Validazione parametri
        try:
            fd = self._from_date.date().toPython()
            td = self._to_date.date().toPython()
            t_start = self._get_arrival_start()
            t_end = self._get_arrival_end()
            bm = self._bucket_spin.value()
            validate_params(fd, td, t_start, t_end, bm)
        except ValueError as exc:
            QMessageBox.critical(self, "Parametri non validi", str(exc))
            return

        pool = self._get_selected_pool()
        if not pool:
            QMessageBox.critical(
                self, "Pool vuoto",
                "Selezionare almeno un dipendente prima di generare il report."
            )
            return

        out_path = self._current_output_path()

        # Verifica file già esistente
        if out_path.exists():
            dlg = QMessageBox(self)
            dlg.setWindowTitle("File già esistente")
            dlg.setText(
                f"Il file esiste già:\n{out_path}\n\n"
                "Vuoi sovrascriverlo, salvare una nuova copia oppure annullare?"
            )
            btn_over  = dlg.addButton("Sovrascrivi",    QMessageBox.ButtonRole.AcceptRole)
            btn_copy  = dlg.addButton("Salva nuova copia", QMessageBox.ButtonRole.ActionRole)
            dlg.addButton("Annulla",         QMessageBox.ButtonRole.RejectRole)
            dlg.setDefaultButton(btn_copy)
            dlg.exec()
            clicked = dlg.clickedButton()
            if clicked == btn_over:
                pass  # sovrascrivi: out_path invariato
            elif clicked == btn_copy:
                out_path = next_available_path(out_path)
                self._name_edit.blockSignals(True)
                self._name_edit.setText(out_path.name)
                self._name_edit.blockSignals(False)
                self._filename_manually_edited = True
            else:
                return  # annullato

        # Avvio worker
        params = ArrivalStatsParams(
            from_day=fd, to_day=td,
            arrival_start=t_start, arrival_end=t_end,
            bucket_minutes=bm,
            employee_pool=pool,
            output_path=out_path,
        )

        self._gen_btn.setEnabled(False)
        self._progress_bar.setValue(0)
        self._result_group.setVisible(False)

        self._report_worker = _ReportWorker(
            self._client, params, self._cfg["timezone"], parent=self
        )
        self._report_worker.progress.connect(self._on_progress)
        self._report_worker.finished.connect(self._on_report_done)
        self._report_worker.error.connect(self._on_report_error)
        self._report_worker.permission_error.connect(self._on_permission_error)
        self._report_worker.start()
        self.statusBar().showMessage("Generazione in corso…")

    @Slot(str, int)
    def _on_progress(self, msg: str, pct: int):
        self._progress_bar.setValue(pct)
        self.statusBar().showMessage(msg)

    @Slot(object)
    def _on_report_done(self, result: ArrivalStatsResult):
        self._gen_btn.setEnabled(True)
        self._progress_bar.setValue(100)
        self._last_output = result.output_path
        ps = result.period_stats
        self._result_label.setText(
            f"File           : {result.output_path}\n"
            f"Dipendenti     : {ps.employee_count}\n"
            f"Ingressi validi: {ps.valid_count}\n"
            f"Esclusi        : {ps.excluded_count}\n"
            f"Media          : {ps.mean_dt.strftime('%H:%M') if ps.mean_dt else 'N/D'}\n"
            f"Mediana        : {ps.median_dt.strftime('%H:%M') if ps.median_dt else 'N/D'}"
        )
        self._result_group.setVisible(True)
        self.statusBar().showMessage("Completato.", 6000)
        QMessageBox.information(
            self, "Report generato",
            f"File salvato in:\n{result.output_path}"
        )

    @Slot(str)
    def _on_report_error(self, msg: str):
        self._gen_btn.setEnabled(True)
        self._progress_bar.setValue(0)
        self.statusBar().showMessage("Errore durante la generazione.")
        QMessageBox.critical(self, "Errore durante la generazione", msg)

    @Slot()
    def _on_permission_error(self):
        self._gen_btn.setEnabled(True)
        self._progress_bar.setValue(0)
        self.statusBar().showMessage("Errore: file non scrivibile.")
        QMessageBox.critical(
            self, "File non scrivibile",
            "Il file di destinazione è già aperto oppure la cartella non è scrivibile.\n\n"
            "Chiudi il file Excel oppure scegli un nome o un percorso differente."
        )

    # ==================================================================
    # Apri cartella / file
    # ==================================================================

    def _open_folder(self):
        if not self._last_output:
            return
        folder = str(self._last_output.parent.resolve())
        try:
            subprocess.Popen(f'explorer "{folder}"')
        except Exception as exc:
            QMessageBox.critical(self, "Apertura fallita", str(exc))

    def _open_file(self):
        if not self._last_output:
            return
        try:
            os.startfile(str(self._last_output.resolve()))
        except Exception as exc:
            QMessageBox.critical(self, "Apertura fallita", str(exc))

    # ==================================================================
    # Reset date
    # ==================================================================

    def _reset_dates(self):
        today = QDate.currentDate()
        self._from_date.setDate(QDate(today.year(), 1, 1))
        self._to_date.setDate(today)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ArrivalStatsAppQt()
    window.show()
    sys.exit(app.exec())
