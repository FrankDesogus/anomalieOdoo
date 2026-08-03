"""
GUI desktop per la generazione del report statistiche ingressi.
Avvio:  .venv\\Scripts\\python.exe arrival_stats_gui.py

Il motore di calcolo e' interamente in:
  app/stats_builder.py
  app/stats_report.py
  app/stats_service.py
Questa GUI non duplica nessuna logica di business.
"""
from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

import yaml

from app.odoo_client import OdooClient
from app.pool_store import Pool, delete_pool, list_pools, load_pool, save_pool, validate_pool_name
from app.stats_service import (
    ArrivalStatsParams,
    ArrivalStatsResult,
    default_output_path,
    fetch_sessions,
    parse_date,
    parse_time,
    resolve_pool_from_ids,
    run_pipeline,
    validate_params,
)

POOLS_DIR = Path("config/pools")
CONFIG_FILE = "config.yaml"


# ---------------------------------------------------------------------------
# Scrollable checkbutton list
# ---------------------------------------------------------------------------

class _ScrollableCheckList(ttk.Frame):
    """A canvas-based scrollable list of checkbuttons, one per employee."""

    def __init__(self, parent, on_change=None, **kwargs):
        super().__init__(parent, **kwargs)
        self._on_change = on_change

        self._canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0)
        vsb = ttk.Scrollbar(self, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        self._inner = ttk.Frame(self._canvas)
        self._win_id = self._canvas.create_window((0, 0), window=self._inner, anchor="nw")

        self._inner.bind("<Configure>", self._on_inner_resize)
        self._canvas.bind("<Configure>", self._on_canvas_resize)
        self._canvas.bind("<Enter>", self._bind_wheel)
        self._canvas.bind("<Leave>", self._unbind_wheel)

        self._vars: dict[int, tk.BooleanVar] = {}
        self._rows: dict[int, ttk.Frame] = {}
        self._employees: list[tuple[int, str]] = []

    # ------------------------------------------------------------------
    def _on_inner_resize(self, _event):
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_resize(self, event):
        self._canvas.itemconfig(self._win_id, width=event.width)

    def _bind_wheel(self, _event):
        self._canvas.bind_all("<MouseWheel>", self._on_wheel)

    def _unbind_wheel(self, _event):
        self._canvas.unbind_all("<MouseWheel>")

    def _on_wheel(self, event):
        self._canvas.yview_scroll(-1 * (event.delta // 120), "units")

    # ------------------------------------------------------------------
    def set_employees(self, employees: list[tuple[int, str]]):
        for w in self._inner.winfo_children():
            w.destroy()
        self._vars.clear()
        self._rows.clear()
        self._employees = sorted(employees, key=lambda e: (e[1] or "").lower())

        for emp_id, name in self._employees:
            var = tk.BooleanVar(value=False)
            if self._on_change:
                var.trace_add("write", lambda *_: self._on_change())
            self._vars[emp_id] = var

            row = ttk.Frame(self._inner)
            row.pack(fill="x", padx=4, pady=1)
            ttk.Checkbutton(
                row, variable=var,
                text=f"{name}  [{emp_id}]",
            ).pack(side="left")
            self._rows[emp_id] = row

    def filter(self, query: str):
        q = query.strip().lower()
        for emp_id, name in self._employees:
            row = self._rows.get(emp_id)
            if row is None:
                continue
            visible = not q or q in name.lower() or q in str(emp_id)
            if visible:
                row.pack(fill="x", padx=4, pady=1)
            else:
                row.pack_forget()

    def get_selected(self) -> list[tuple[int, str]]:
        return [(eid, n) for eid, n in self._employees if self._vars[eid].get()]

    def get_selected_ids(self) -> set[int]:
        return {eid for eid, _ in self._employees if self._vars[eid].get()}

    def set_selected_ids(self, ids: set[int]):
        for eid, var in self._vars.items():
            var.set(eid in ids)

    def select_visible(self):
        for emp_id, row in self._rows.items():
            if row.winfo_manager():
                self._vars[emp_id].set(True)

    def deselect_all(self):
        for var in self._vars.values():
            var.set(False)

    def count_selected(self) -> int:
        return sum(1 for v in self._vars.values() if v.get())


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------

class ArrivalStatsApp(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("Statistiche Orari di Ingresso")
        self.geometry("960x820")
        self.minsize(820, 640)
        self.resizable(True, True)

        self._cfg: dict | None = None
        self._client: OdooClient | None = None
        self._all_employees: list[tuple[int, str]] = []

        self._init_queue: queue.Queue = queue.Queue()
        self._work_queue: queue.Queue = queue.Queue()

        self._build_ui()
        self._load_odoo_async()

    # ==================================================================
    # UI construction
    # ==================================================================

    def _build_ui(self):
        # Outer scrollable canvas (for small screens)
        outer = ttk.Frame(self, padding=0)
        outer.pack(fill="both", expand=True)

        canvas = tk.Canvas(outer, borderwidth=0, highlightthickness=0)
        vsb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        self._main = ttk.Frame(canvas, padding=10)
        win_id = canvas.create_window((0, 0), window=self._main, anchor="nw")

        def _on_resize(event):
            canvas.itemconfig(win_id, width=event.width)
        canvas.bind("<Configure>", _on_resize)
        self._main.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Enter>", lambda _e: canvas.bind_all("<MouseWheel>",
                    lambda ev: canvas.yview_scroll(-1 * (ev.delta // 120), "units")))
        canvas.bind("<Leave>", lambda _e: canvas.unbind_all("<MouseWheel>"))

        self._build_periodo(self._main)
        self._build_finestra(self._main)
        self._build_dipendenti_e_pool(self._main)
        self._build_output(self._main)
        self._build_preview(self._main)
        self._build_generate(self._main)
        self._build_result(self._main)

    # ------------------------------------------------------------------
    def _build_periodo(self, parent):
        frm = ttk.LabelFrame(parent, text="Periodo di analisi", padding=8)
        frm.pack(fill="x", pady=(0, 6))

        today = date.today()
        self._from_var = tk.StringVar(value=str(date(today.year, 1, 1)))
        self._to_var = tk.StringVar(value=str(today))

        self._from_var.trace_add("write", lambda *_: self._on_period_changed())
        self._to_var.trace_add("write", lambda *_: self._on_period_changed())

        ttk.Label(frm, text="Data iniziale (YYYY-MM-DD):").grid(row=0, column=0, sticky="w", padx=(0, 4))
        ttk.Entry(frm, textvariable=self._from_var, width=13).grid(row=0, column=1, padx=4)
        ttk.Label(frm, text="Data finale (YYYY-MM-DD):").grid(row=0, column=2, sticky="w", padx=(12, 4))
        ttk.Entry(frm, textvariable=self._to_var, width=13).grid(row=0, column=3, padx=4)
        ttk.Button(frm, text="Da gennaio a oggi", command=self._reset_dates).grid(
            row=0, column=4, padx=(16, 0))

    # ------------------------------------------------------------------
    def _build_finestra(self, parent):
        frm = ttk.LabelFrame(parent, text="Finestra ingressi validi", padding=8)
        frm.pack(fill="x", pady=(0, 6))

        self._start_var = tk.StringVar(value="08:00")
        self._end_var = tk.StringVar(value="09:00")
        self._bucket_var = tk.StringVar(value="10")

        for v in (self._start_var, self._end_var, self._bucket_var):
            v.trace_add("write", lambda *_: self._schedule_preview())

        ttk.Label(frm, text="Ingresso minimo (HH:MM):").grid(row=0, column=0, sticky="w", padx=(0, 4))
        ttk.Entry(frm, textvariable=self._start_var, width=7).grid(row=0, column=1, padx=4)
        ttk.Label(frm, text="Ingresso massimo (HH:MM):").grid(row=0, column=2, sticky="w", padx=(12, 4))
        ttk.Entry(frm, textvariable=self._end_var, width=7).grid(row=0, column=3, padx=4)
        ttk.Label(frm, text="Ampiezza fasce (min):").grid(row=0, column=4, sticky="w", padx=(12, 4))
        ttk.Spinbox(frm, textvariable=self._bucket_var, from_=1, to=60, width=5).grid(
            row=0, column=5, padx=4)

    # ------------------------------------------------------------------
    def _build_dipendenti_e_pool(self, parent):
        outer = ttk.Frame(parent)
        outer.pack(fill="both", expand=True, pady=(0, 6))
        outer.columnconfigure(0, weight=3)
        outer.columnconfigure(1, weight=1)

        # ---- Dipendenti (left) ----
        emp_frm = ttk.LabelFrame(outer, text="Selezione dipendenti", padding=8)
        emp_frm.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        emp_frm.rowconfigure(1, weight=1)
        emp_frm.columnconfigure(0, weight=1)

        search_row = ttk.Frame(emp_frm)
        search_row.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        ttk.Label(search_row, text="Cerca:").pack(side="left", padx=(0, 4))
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._filter_employees())
        ttk.Entry(search_row, textvariable=self._search_var, width=20).pack(side="left", padx=(0, 8))
        ttk.Button(search_row, text="Seleziona visibili", command=self._select_visible).pack(side="left", padx=4)
        ttk.Button(search_row, text="Deseleziona tutti", command=self._deselect_all).pack(side="left", padx=4)

        self._checklist = _ScrollableCheckList(emp_frm, on_change=self._on_selection_changed)
        self._checklist.grid(row=1, column=0, sticky="nsew")
        self._checklist.configure(height=260)

        self._counter_var = tk.StringVar(value="Selezionati: 0")
        self._init_label = ttk.Label(emp_frm, text="Connessione a Odoo in corso...", foreground="gray")
        self._init_label.grid(row=2, column=0, sticky="w", pady=(4, 0))
        ttk.Label(emp_frm, textvariable=self._counter_var, foreground="navy").grid(
            row=3, column=0, sticky="w")

        # ---- Pool (right) ----
        pool_frm = ttk.LabelFrame(outer, text="Pool dipendenti", padding=8)
        pool_frm.grid(row=0, column=1, sticky="nsew")
        pool_frm.columnconfigure(0, weight=1)

        ttk.Label(pool_frm, text="Pool salvati:").grid(row=0, column=0, sticky="w")
        self._pool_combo = ttk.Combobox(pool_frm, state="readonly", width=18)
        self._pool_combo.grid(row=1, column=0, sticky="ew", pady=(0, 6))

        ttk.Button(pool_frm, text="Carica pool", command=self._load_pool).grid(
            row=2, column=0, sticky="ew", pady=2)
        ttk.Button(pool_frm, text="Salva come nuovo pool", command=self._save_pool_as).grid(
            row=3, column=0, sticky="ew", pady=2)
        ttk.Button(pool_frm, text="Aggiorna pool", command=self._update_pool).grid(
            row=4, column=0, sticky="ew", pady=2)
        ttk.Button(pool_frm, text="Elimina pool", command=self._delete_pool).grid(
            row=5, column=0, sticky="ew", pady=2)

        self._refresh_pool_list()

    # ------------------------------------------------------------------
    def _build_output(self, parent):
        frm = ttk.LabelFrame(parent, text="Output", padding=8)
        frm.pack(fill="x", pady=(0, 6))
        frm.columnconfigure(1, weight=1)

        self._out_dir_var = tk.StringVar(value="reports")
        self._out_name_var = tk.StringVar()
        self._update_filename_from_dates()

        ttk.Label(frm, text="Cartella:").grid(row=0, column=0, sticky="w", padx=(0, 4))
        ttk.Entry(frm, textvariable=self._out_dir_var).grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Button(frm, text="Sfoglia", command=self._browse_folder).grid(row=0, column=2, padx=(4, 0))

        ttk.Label(frm, text="Nome file:").grid(row=1, column=0, sticky="w", padx=(0, 4), pady=(4, 0))
        ttk.Entry(frm, textvariable=self._out_name_var).grid(
            row=1, column=1, sticky="ew", padx=4, pady=(4, 0))

    # ------------------------------------------------------------------
    def _build_preview(self, parent):
        frm = ttk.LabelFrame(parent, text="Anteprima parametri", padding=8)
        frm.pack(fill="x", pady=(0, 6))
        self._preview_var = tk.StringVar(value="—")
        ttk.Label(frm, textvariable=self._preview_var, justify="left",
                  font=("Courier", 9)).pack(anchor="w")

    # ------------------------------------------------------------------
    def _build_generate(self, parent):
        frm = ttk.Frame(parent)
        frm.pack(fill="x", pady=(0, 6))

        self._gen_btn = ttk.Button(
            frm, text="  GENERA REPORT EXCEL  ",
            command=self._generate_report,
            style="Accent.TButton",
        )
        self._gen_btn.pack(side="left", padx=(0, 12))

        self._progress = ttk.Progressbar(frm, mode="determinate", length=220)
        self._progress.pack(side="left", padx=(0, 8))
        self._progress_var = tk.DoubleVar(value=0)
        self._progress.configure(variable=self._progress_var)

        self._status_var = tk.StringVar(value="In attesa...")
        ttk.Label(frm, textvariable=self._status_var, foreground="gray").pack(side="left")

    # ------------------------------------------------------------------
    def _build_result(self, parent):
        self._result_frm = ttk.LabelFrame(parent, text="Risultato", padding=8)
        # Not packed initially

        self._result_text = tk.StringVar()
        ttk.Label(self._result_frm, textvariable=self._result_text, justify="left",
                  font=("Courier", 9)).grid(row=0, column=0, columnspan=2, sticky="w")

        ttk.Button(self._result_frm, text="Apri cartella",
                   command=self._open_folder).grid(row=1, column=0, padx=(0, 8), pady=(8, 0))
        ttk.Button(self._result_frm, text="Apri file Excel",
                   command=self._open_file).grid(row=1, column=1, pady=(8, 0))

        self._last_output: Path | None = None

    # ==================================================================
    # Odoo loading
    # ==================================================================

    def _load_odoo_async(self):
        threading.Thread(target=self._fetch_employees_worker, daemon=True).start()
        self._poll_init_queue()

    def _fetch_employees_worker(self):
        try:
            cfg = yaml.safe_load(open(CONFIG_FILE, "r", encoding="utf-8"))
            o = cfg["odoo"]
            client = OdooClient(o["url"], o["db"], o["user"], o["password"], cfg["timezone"])
            employees = client.fetch_active_employees()
            self._init_queue.put(("ok", cfg, client, employees))
        except Exception as exc:
            self._init_queue.put(("error", str(exc)))

    def _poll_init_queue(self):
        try:
            msg = self._init_queue.get_nowait()
            if msg[0] == "ok":
                _, cfg, client, employees = msg
                self._cfg = cfg
                self._client = client
                self._all_employees = employees
                self._checklist.set_employees(employees)
                self._init_label.configure(
                    text=f"Connesso. {len(employees)} dipendenti attivi.", foreground="green")
                self._status_var.set("Pronto.")
                self._update_counter()
                self._schedule_preview()
            else:
                err = msg[1]
                self._init_label.configure(
                    text=f"Errore connessione: {err}", foreground="red")
                self._status_var.set("Connessione Odoo fallita.")
                messagebox.showerror(
                    "Errore connessione Odoo",
                    f"{err}\n\nVerificare config.yaml (url, db, user, password)."
                )
            return
        except queue.Empty:
            pass
        self.after(200, self._poll_init_queue)

    # ==================================================================
    # Employee list interactions
    # ==================================================================

    def _filter_employees(self):
        self._checklist.filter(self._search_var.get())

    def _on_selection_changed(self):
        self._update_counter()
        self._schedule_preview()

    def _update_counter(self):
        n = self._checklist.count_selected()
        self._counter_var.set(f"Selezionati: {n}")

    def _select_visible(self):
        self._checklist.select_visible()

    def _deselect_all(self):
        self._checklist.deselect_all()

    # ==================================================================
    # Pool management
    # ==================================================================

    def _refresh_pool_list(self):
        pools = list_pools(POOLS_DIR)
        self._pool_combo["values"] = pools
        if pools and not self._pool_combo.get():
            self._pool_combo.set(pools[0])

    def _load_pool(self):
        name = self._pool_combo.get()
        if not name:
            messagebox.showwarning("Pool", "Nessun pool selezionato.")
            return
        try:
            pool = load_pool(name, POOLS_DIR)
        except FileNotFoundError as exc:
            messagebox.showerror("Pool non trovato", str(exc))
            return

        # Select active IDs; warn about missing ones
        active = {eid: n for eid, n in self._all_employees}
        valid_pool, missing = resolve_pool_from_ids(pool.employee_ids, active)
        self._checklist.set_selected_ids({eid for eid, _ in valid_pool})

        if missing:
            messagebox.showwarning(
                "ID non piu' attivi",
                f"Pool '{name}' caricato.\n\n"
                f"I seguenti ID non sono piu' presenti tra i dipendenti attivi e sono stati ignorati:\n"
                f"{missing}"
            )
        else:
            self._status_var.set(f"Pool '{name}' caricato ({len(valid_pool)} dipendenti).")

    def _save_pool_as(self):
        selected = self._checklist.get_selected()
        if not selected:
            messagebox.showwarning("Pool vuoto", "Selezionare almeno un dipendente prima di salvare.")
            return
        name = simpledialog.askstring(
            "Nome pool", "Inserire il nome del nuovo pool:",
            parent=self
        )
        if not name:
            return
        try:
            validate_pool_name(name)
        except ValueError as exc:
            messagebox.showerror("Nome non valido", str(exc))
            return
        pool = Pool(name=name, employee_ids=[eid for eid, _ in selected])
        save_pool(pool, POOLS_DIR)
        self._refresh_pool_list()
        self._pool_combo.set(name)
        self._status_var.set(f"Pool '{name}' salvato ({len(selected)} dipendenti).")

    def _update_pool(self):
        name = self._pool_combo.get()
        if not name:
            messagebox.showwarning("Pool", "Nessun pool selezionato.")
            return
        selected = self._checklist.get_selected()
        if not selected:
            messagebox.showwarning("Pool vuoto", "Selezionare almeno un dipendente prima di aggiornare.")
            return
        if not messagebox.askyesno("Aggiorna pool", f"Sovrascrivere il pool '{name}' con la selezione attuale?"):
            return
        pool = Pool(name=name, employee_ids=[eid for eid, _ in selected])
        save_pool(pool, POOLS_DIR)
        self._status_var.set(f"Pool '{name}' aggiornato ({len(selected)} dipendenti).")

    def _delete_pool(self):
        name = self._pool_combo.get()
        if not name:
            messagebox.showwarning("Pool", "Nessun pool selezionato.")
            return
        if not messagebox.askyesno("Elimina pool", f"Eliminare definitivamente il pool '{name}'?"):
            return
        try:
            delete_pool(name, POOLS_DIR)
        except FileNotFoundError as exc:
            messagebox.showerror("Errore", str(exc))
            return
        self._refresh_pool_list()
        self._status_var.set(f"Pool '{name}' eliminato.")

    # ==================================================================
    # Output helpers
    # ==================================================================

    def _browse_folder(self):
        folder = filedialog.askdirectory(title="Scegli cartella di destinazione")
        if folder:
            self._out_dir_var.set(folder)

    def _update_filename_from_dates(self):
        try:
            fd = parse_date(self._from_var.get())
            td = parse_date(self._to_var.get())
            self._out_name_var.set(f"statistiche_ingressi_{fd}_{td}.xlsx")
        except (ValueError, AttributeError):
            pass

    def _on_period_changed(self):
        self._update_filename_from_dates()
        self._schedule_preview()

    # ==================================================================
    # Preview
    # ==================================================================

    _preview_job = None

    def _schedule_preview(self, *_args):
        if self._preview_job:
            self.after_cancel(self._preview_job)
        self._preview_job = self.after(250, self._update_preview)

    def _update_preview(self):
        self._preview_job = None
        n = self._checklist.count_selected()
        out = Path(self._out_dir_var.get()) / self._out_name_var.get()
        try:
            fd = parse_date(self._from_var.get())
            td = parse_date(self._to_var.get())
            ws = self._start_var.get()
            we = self._end_var.get()
            bm = self._bucket_var.get()
            self._preview_var.set(
                f"Dipendenti selezionati : {n}\n"
                f"Periodo                : {fd} -> {td}\n"
                f"Finestra valida        : {ws} -> {we}\n"
                f"Fasce statistiche      : {bm} minuti\n"
                f"Output                 : {out}"
            )
        except Exception:
            self._preview_var.set("(parametri non validi)")

    # ==================================================================
    # Report generation
    # ==================================================================

    def _generate_report(self):
        # Validation
        if self._cfg is None:
            messagebox.showerror("Odoo non connesso", "Attendere il completamento della connessione a Odoo.")
            return

        try:
            from_day = parse_date(self._from_var.get())
            to_day = parse_date(self._to_var.get())
            arrival_start = parse_time(self._start_var.get())
            arrival_end = parse_time(self._end_var.get())
            bucket_minutes = int(self._bucket_var.get())
            validate_params(from_day, to_day, arrival_start, arrival_end, bucket_minutes)
        except (ValueError, TypeError) as exc:
            messagebox.showerror("Parametri non validi", str(exc))
            return

        pool = self._checklist.get_selected()
        if not pool:
            messagebox.showerror(
                "Pool vuoto",
                "Selezionare almeno un dipendente prima di generare il report."
            )
            return

        out_path = Path(self._out_dir_var.get()) / self._out_name_var.get()
        params = ArrivalStatsParams(
            from_day=from_day, to_day=to_day,
            arrival_start=arrival_start, arrival_end=arrival_end,
            bucket_minutes=bucket_minutes,
            employee_pool=pool,
            output_path=out_path,
        )

        # Hide previous result
        self._result_frm.pack_forget()
        self._gen_btn.configure(state="disabled")
        self._progress_var.set(0)

        threading.Thread(target=self._worker, args=(params,), daemon=True).start()
        self._poll_work_queue()

    def _worker(self, params: ArrivalStatsParams):
        try:
            self._work_queue.put(("status", "Connessione a Odoo...", 10))
            client = self._client
            if client is None:
                raise RuntimeError("Client Odoo non inizializzato.")

            self._work_queue.put(("status", "Recupero timbrature...", 30))
            sessions = fetch_sessions(
                client, params.from_day, params.to_day, self._cfg["timezone"]
            )

            self._work_queue.put(("status", "Calcolo statistiche...", 65))
            result = run_pipeline(sessions, params)

            self._work_queue.put(("status", "Report Excel generato.", 100))
            self._work_queue.put(("done", result))
        except Exception as exc:
            self._work_queue.put(("error", str(exc)))

    def _poll_work_queue(self):
        try:
            while True:
                msg = self._work_queue.get_nowait()
                kind = msg[0]
                if kind == "status":
                    _, text, pct = msg
                    self._status_var.set(text)
                    self._progress_var.set(pct)
                elif kind == "done":
                    self._on_done(msg[1])
                    return
                elif kind == "error":
                    self._on_error(msg[1])
                    return
        except queue.Empty:
            pass
        self.after(100, self._poll_work_queue)

    def _on_done(self, result: ArrivalStatsResult):
        self._gen_btn.configure(state="normal")
        self._progress_var.set(100)
        ps = result.period_stats
        self._last_output = result.output_path
        self._result_text.set(
            f"File         : {result.output_path}\n"
            f"Dipendenti   : {ps.employee_count}\n"
            f"Ingressi validi   : {ps.valid_count}\n"
            f"Esclusi fuori fascia : {ps.excluded_count}\n"
            f"Media        : {ps.mean_dt.strftime('%H:%M') if ps.mean_dt else 'N/D'}\n"
            f"Mediana      : {ps.median_dt.strftime('%H:%M') if ps.median_dt else 'N/D'}"
        )
        self._result_frm.pack(fill="x", pady=(6, 0))
        self._status_var.set("Completato.")
        messagebox.showinfo(
            "Report generato",
            f"File salvato in:\n{result.output_path}"
        )

    def _on_error(self, msg: str):
        self._gen_btn.configure(state="normal")
        self._progress_var.set(0)
        self._status_var.set("Errore.")
        messagebox.showerror("Errore durante la generazione", msg)

    # ==================================================================
    # Open folder / file (Windows)
    # ==================================================================

    def _open_folder(self):
        if not self._last_output:
            return
        folder = str(self._last_output.parent.resolve())
        try:
            subprocess.Popen(f'explorer "{folder}"')
        except Exception as exc:
            messagebox.showerror("Apertura fallita", str(exc))

    def _open_file(self):
        if not self._last_output:
            return
        try:
            os.startfile(str(self._last_output.resolve()))
        except Exception as exc:
            messagebox.showerror("Apertura fallita", str(exc))

    # ==================================================================
    # Date reset
    # ==================================================================

    def _reset_dates(self):
        today = date.today()
        self._from_var.set(str(date(today.year, 1, 1)))
        self._to_var.set(str(today))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = ArrivalStatsApp()
    app.mainloop()
