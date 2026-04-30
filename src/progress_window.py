"""
progress_window.py — Fenêtre flottante de progression du traitement (tkinter)

Créer une instance puis lancer dans un thread daemon :
    win = ProgressWindow(on_cancel=process.cancel)
    threading.Thread(target=win.mainloop, daemon=True).start()

Mettre à jour depuis n'importe quel thread :
    win.on_event(ProgressEvent(step="transcription", pct=0.5, message="..."))
"""

import tkinter as tk
from tkinter import ttk
import threading
import time
import os


class ProgressWindow:
    def __init__(self, on_cancel):
        self._on_cancel = on_cancel
        self._root = None
        self._start_time = time.monotonic()
        self._step_label = None
        self._pct_label = None
        self._msg_label = None
        self._timer_label = None
        self._progress_bar = None
        self._cancel_btn = None
        self._finished = False

    def mainloop(self) -> None:
        """Crée la fenêtre et lance la boucle tkinter. Doit tourner dans son propre thread."""
        self._root = tk.Tk()
        self._root.title("Meeting Recorder")
        self._root.resizable(False, False)
        self._root.attributes("-topmost", True)
        self._root.attributes("-toolwindow", True)
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._setup_ui()
        self._tick()
        self._root.mainloop()

    def _setup_ui(self) -> None:
        frame = ttk.Frame(self._root, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Meeting Recorder", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W)
        ttk.Separator(frame).pack(fill=tk.X, pady=8)

        self._step_label = ttk.Label(frame, text="Initialisation...", font=("Segoe UI", 9))
        self._step_label.pack(anchor=tk.W)

        self._progress_bar = ttk.Progressbar(frame, length=280, mode="indeterminate")
        self._progress_bar.pack(fill=tk.X, pady=(4, 2))
        self._progress_bar.start(10)

        self._pct_label = ttk.Label(frame, text="", font=("Segoe UI", 8), foreground="#666666")
        self._pct_label.pack(anchor=tk.E)

        self._msg_label = ttk.Label(frame, text="", font=("Segoe UI", 8), foreground="#444444", wraplength=280)
        self._msg_label.pack(anchor=tk.W, pady=(4, 0))

        self._timer_label = ttk.Label(frame, text="⏱ 0 s", font=("Segoe UI", 8), foreground="#888888")
        self._timer_label.pack(anchor=tk.W, pady=(8, 0))

        ttk.Separator(frame).pack(fill=tk.X, pady=8)

        self._cancel_btn = ttk.Button(frame, text="Annuler", command=self._do_cancel)
        self._cancel_btn.pack(anchor=tk.E)

        self._root.update_idletasks()
        w = self._root.winfo_reqwidth()
        h = self._root.winfo_reqheight()
        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self._root.geometry(f"{w}x{h}+{x}+{y}")

    def _tick(self) -> None:
        if self._finished or self._root is None:
            return
        elapsed = int(time.monotonic() - self._start_time)
        text = f"⏱ {elapsed // 60} min {elapsed % 60} s" if elapsed >= 60 else f"⏱ {elapsed} s"
        if self._timer_label:
            self._timer_label.config(text=text)
        self._root.after(1000, self._tick)

    def _do_cancel(self) -> None:
        if self._cancel_btn:
            self._cancel_btn.config(state=tk.DISABLED, text="Annulation...")
        threading.Thread(target=self._on_cancel, daemon=True).start()

    def _on_close(self) -> None:
        self._finished = True
        root = self._root
        self._root = None
        if root:
            root.destroy()

    def on_event(self, event) -> None:
        """Thread-safe : peut être appelé depuis n'importe quel thread."""
        if self._root is None:
            return
        self._root.after(0, lambda e=event: self._handle_event(e))

    def _handle_event(self, event) -> None:
        if self._root is None:
            return
        _LABELS = {
            "transcription": "Transcription",
            "alignment": "Alignement temporel",
            "diarization": "Diarisation",
            "gemini": "Génération du compte rendu",
            "done": "Terminé",
            "error": "Erreur",
        }
        self._step_label.config(text=_LABELS.get(event.step, event.step))
        self._msg_label.config(text=event.message, foreground="#444444")

        if event.step == "done":
            self._show_done()
            return
        if event.step == "error":
            self._show_error(event.message)
            return

        if event.pct < 0:
            if self._progress_bar["mode"] != "indeterminate":
                self._progress_bar.config(mode="indeterminate")
                self._progress_bar.start(10)
            self._pct_label.config(text="")
        else:
            self._progress_bar.stop()
            self._progress_bar.config(mode="determinate", value=int(event.pct * 100))
            self._pct_label.config(text=f"{int(event.pct * 100)}%")

    def _show_done(self) -> None:
        self._finished = True
        if self._step_label:
            self._step_label.config(text="✅ Terminé")
        if self._progress_bar:
            self._progress_bar.stop()
            self._progress_bar.config(mode="determinate", value=100)
        if self._cancel_btn:
            self._cancel_btn.config(state=tk.DISABLED)
        if self._root:
            self._root.after(2000, self._root.destroy)

    def _show_error(self, message: str) -> None:
        self._finished = True
        if self._step_label:
            self._step_label.config(text="❌ Erreur")
        if self._msg_label:
            self._msg_label.config(text=message, foreground="red")
        if self._progress_bar:
            self._progress_bar.stop()
        if self._cancel_btn:
            self._cancel_btn.config(text="Ouvrir tray.log", command=self._open_log, state=tk.NORMAL)

    def _open_log(self) -> None:
        log_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tray.log"))
        os.startfile(log_path)

    @property
    def is_alive(self) -> bool:
        """True si la fenêtre existe encore (non fermée manuellement ni par done/error)."""
        return self._root is not None

    def lift(self) -> None:
        """Ramène la fenêtre au premier plan si elle existe encore."""
        if self._root:
            self._root.after(0, lambda: (self._root.lift(), self._root.focus_force()) if self._root else None)
