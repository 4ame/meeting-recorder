# UX Progression & Contrôle du Traitement — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter progression visible, fenêtre flottante tkinter, annulation propre et notifications enrichies au pipeline meeting-recorder.

**Architecture:** `process.py` publie des `ProgressEvent` via callback optionnel `on_progress`. `whisperx_worker.py` émet des JSON de progression sur stderr, lus en temps réel par `process.py` via un thread daemon. `tray.py` compose un callback qui dispatche vers le tooltip tray et une `ProgressWindow` tkinter.

**Tech Stack:** Python 3.14, tkinter (stdlib), subprocess.Popen, threading, dataclasses, pytest

---

## Carte des fichiers

| Fichier | Action | Responsabilité |
|---|---|---|
| `src/process.py` | Modifier | Ajouter `ProgressEvent`, `ProcessCancelled`, `cancel()`, `_reset_cancel()`, `_last_model_used` ; refactoriser `transcribe_whisperx` avec Popen + thread stderr ; ajouter callbacks dans `transcribe_whisper` et `generate_report_from_text` |
| `src/whisperx_worker.py` | Modifier | Ajouter `_emit()` helper + 7 appels aux points clés du pipeline |
| `src/progress_window.py` | Créer | Fenêtre tkinter non-redimensionnable avec barre de progression, chronomètre, bouton Annuler |
| `src/tray.py` | Modifier | Ajouter globaux `_processing`/`_progress_win`, callback composite, tooltip dynamique, menu Processing, notifications enrichies, tray.log en append |
| `tests/conftest.py` | Créer | Ajoute `src/` au sys.path pour pytest |
| `tests/test_process.py` | Créer | Tests unitaires : ProgressEvent, cancel(), ProcessCancelled |
| `requirements.txt` | Modifier | Ajouter `pytest>=8.0.0` |

---

### Task 1 : Infrastructure de test + dataclass ProgressEvent

**Files:**
- Modify: `requirements.txt`
- Create: `tests/conftest.py`
- Create: `tests/test_process.py`
- Modify: `src/process.py` (ajouter imports + ProgressEvent + ProcessCancelled en tête de fichier)

- [ ] **Étape 1 : Ajouter pytest à requirements.txt**

Ouvrir `requirements.txt` et ajouter à la fin :
```
pytest>=8.0.0
```

- [ ] **Étape 2 : Créer tests/conftest.py**

```python
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
```

- [ ] **Étape 3 : Ajouter ProgressEvent et ProcessCancelled dans process.py**

Après les imports existants (ligne ~18, après `from pathlib import Path`), ajouter :

```python
from dataclasses import dataclass

@dataclass
class ProgressEvent:
    step: str     # "transcription"|"alignment"|"diarization"|"gemini"|"done"|"error"
    pct: float    # 0.0–1.0 ; -1.0 = indéterminé (progressbar en mode bounce)
    message: str  # description courte affichée dans l'UI


class ProcessCancelled(Exception):
    pass
```

- [ ] **Étape 4 : Créer tests/test_process.py**

```python
import pytest
import process


def test_progress_event_fields():
    e = process.ProgressEvent(step="transcription", pct=0.5, message="test")
    assert e.step == "transcription"
    assert e.pct == 0.5
    assert e.message == "test"


def test_progress_event_indeterminate_sentinel():
    e = process.ProgressEvent(step="gemini", pct=-1.0, message="")
    assert e.pct < 0


def test_process_cancelled_is_exception():
    with pytest.raises(process.ProcessCancelled):
        raise process.ProcessCancelled("annulé")
```

- [ ] **Étape 5 : Vérifier que les tests passent**

```
cd "C:\Users\arnau\Documents\Projets perso\meeting-recorder"
D:\Utilitaires\Python\python.exe -m pytest tests/test_process.py -v
```

Attendu : 3 tests PASSED

- [ ] **Étape 6 : Commit**

```bash
git add requirements.txt tests/conftest.py tests/test_process.py src/process.py
git commit -m "feat: add ProgressEvent dataclass and ProcessCancelled exception"
```

---

### Task 2 : cancel(), _reset_cancel(), _last_model_used dans process.py

**Files:**
- Modify: `src/process.py`
- Modify: `tests/test_process.py`

- [ ] **Étape 1 : Ajouter les globaux et fonctions dans process.py**

Après la définition de `ProcessCancelled` (juste après les deux nouvelles classes), ajouter :

```python
_cancel_requested: bool = False
_current_proc = None  # subprocess.Popen actif, None sinon
_last_model_used: str = ""  # rempli par generate_report_from_text


def cancel() -> None:
    """Interrompt le traitement en cours : termine le subprocess WhisperX et lève le flag."""
    global _cancel_requested, _current_proc
    _cancel_requested = True
    if _current_proc is not None:
        try:
            _current_proc.terminate()
        except OSError:
            pass
        _current_proc = None


def _reset_cancel() -> None:
    """Remet le flag à zéro avant chaque nouveau traitement."""
    global _cancel_requested
    _cancel_requested = False


def _emit(on_progress, step: str, pct: float, message: str) -> None:
    """Appelle le callback on_progress si présent."""
    if on_progress is not None:
        on_progress(ProgressEvent(step=step, pct=pct, message=message))
```

- [ ] **Étape 2 : Ajouter les tests dans tests/test_process.py**

Ajouter à la fin du fichier :

```python
def test_cancel_sets_flag():
    process._reset_cancel()
    assert not process._cancel_requested
    process.cancel()
    assert process._cancel_requested
    process._reset_cancel()


def test_reset_cancel_clears_flag():
    process._cancel_requested = True
    process._reset_cancel()
    assert not process._cancel_requested


def test_emit_calls_callback():
    events = []
    process._emit(events.append, "transcription", 0.5, "test msg")
    assert len(events) == 1
    assert events[0].step == "transcription"
    assert events[0].pct == 0.5


def test_emit_noop_without_callback():
    process._emit(None, "transcription", 0.0, "msg")  # doit ne pas lever d'exception
```

- [ ] **Étape 3 : Vérifier que les tests passent**

```
D:\Utilitaires\Python\python.exe -m pytest tests/test_process.py -v
```

Attendu : 7 tests PASSED

- [ ] **Étape 4 : Commit**

```bash
git add src/process.py tests/test_process.py
git commit -m "feat: add cancel(), _reset_cancel(), _emit() to process.py"
```

---

### Task 3 : whisperx_worker.py — émission des événements de progression

**Files:**
- Modify: `src/whisperx_worker.py`

- [ ] **Étape 1 : Ajouter le helper _emit() dans whisperx_worker.py**

Après les imports (après la ligne `import os`, avant `def main():`), ajouter :

```python
def _emit(step: str, pct: float, message: str) -> None:
    """Émet un événement de progression sur stderr en JSON. Ne lève jamais d'exception."""
    try:
        line = json.dumps({"type": "progress", "step": step, "pct": pct, "message": message}, ensure_ascii=False)
        print(line, file=sys.stderr, flush=True)
    except Exception:
        pass
```

- [ ] **Étape 2 : Ajouter les 7 appels dans main()**

Modifier la fonction `main()` pour intercaler les appels `_emit`. Voici le bloc modifié depuis `device = ...` jusqu'à la fin du pipeline (avant la construction de `transcription`) :

```python
    device = "cuda" if torch.cuda.is_available() else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"

    # Étape 1 — Transcription
    _emit("transcription", 0.0, "Chargement modèle large-v3-turbo...")
    model = whisperx.load_model("large-v3-turbo", device=device, compute_type=compute_type, language="fr")
    _emit("transcription", 0.3, "Transcription en cours...")
    audio = whisperx.load_audio(audio_path)
    result = model.transcribe(audio, batch_size=16, language="fr")
    _emit("transcription", 0.7, "Transcription terminée")

    # Libère la VRAM avant l'alignement
    del model
    torch.cuda.empty_cache()

    # Étape 2 — Alignement temporel mot à mot
    _emit("alignment", 0.0, "Chargement modèle d'alignement...")
    model_a, metadata = whisperx.load_align_model(language_code="fr", device=device)
    result = whisperx.align(result["segments"], model_a, metadata, audio, device, return_char_alignments=False)
    _emit("alignment", 1.0, "Alignement terminé")

    del model_a
    torch.cuda.empty_cache()

    # Étape 3 — Diarisation (optionnelle si token HuggingFace disponible)
    if hf_token:
        _emit("diarization", 0.0, "Diarisation en cours...")
        diarize_model = whisperx.diarize.DiarizationPipeline(
            model_name="pyannote/speaker-diarization-3.1",
            token=hf_token,
            device=device
        )
        diarize_segments = diarize_model(audio)
        result = whisperx.assign_word_speakers(diarize_segments, result)
        _emit("diarization", 1.0, "Diarisation terminée")
```

- [ ] **Étape 3 : Vérifier manuellement le format de sortie**

Créer un petit fichier WAV de test (ou utiliser un existant dans `recordings/`) et lancer :

```
venv-whisperx\Scripts\python.exe -X utf8 src\whisperx_worker.py recordings\<fichier>.wav 2>stderr_test.txt
type stderr_test.txt | findstr "progress"
```

Attendu : lignes du type `{"type": "progress", "step": "transcription", "pct": 0.0, "message": "Chargement modèle large-v3-turbo..."}` dans stderr_test.txt.

- [ ] **Étape 4 : Commit**

```bash
git add src/whisperx_worker.py
git commit -m "feat: emit JSON progress events on stderr in whisperx_worker"
```

---

### Task 4 : process.py — Popen + thread stderr dans transcribe_whisperx

**Files:**
- Modify: `src/process.py`

- [ ] **Étape 1 : Ajouter threading aux imports en tête de process.py**

La ligne `import threading` n'est pas encore dans process.py. Ajouter après `import sys` :

```python
import threading
```

- [ ] **Étape 2 : Remplacer transcribe_whisperx par la version Popen**

Remplacer la totalité de la fonction `transcribe_whisperx` (lignes 102–132) par :

```python
def transcribe_whisperx(audio_path: str, on_progress=None) -> str:
    """Transcrit via WhisperX (venv Python 3.12) avec alignement et diarisation."""
    import subprocess
    import json as _json
    from subprocess import PIPE
    global _current_proc

    print(f"\n🎙️  Transcription WhisperX (large-v3-turbo + diarisation)")
    print(f"   Fichier : {os.path.basename(audio_path)}")
    print("   ⏳ En cours...")

    _emit(on_progress, "transcription", 0.0, "Lancement WhisperX...")

    cmd = [WHISPERX_PYTHON, "-X", "utf8", WHISPERX_WORKER, audio_path]
    if HF_TOKEN:
        cmd.append(HF_TOKEN)

    env = os.environ.copy()
    ffmpeg_bin = r"C:\Users\arnau\scoop\apps\ffmpeg\current\bin"
    env["PATH"] = ffmpeg_bin + os.pathsep + env.get("PATH", "")

    proc = subprocess.Popen(cmd, stdout=PIPE, stderr=PIPE, env=env)
    _current_proc = proc
    stderr_lines: list[str] = []

    def _read_stderr() -> None:
        for raw in proc.stderr:
            line = raw.decode("utf-8", errors="replace").rstrip()
            stderr_lines.append(line)
            if on_progress:
                try:
                    data = _json.loads(line)
                    if data.get("type") == "progress":
                        on_progress(ProgressEvent(
                            step=data["step"],
                            pct=data["pct"],
                            message=data.get("message", ""),
                        ))
                except (_json.JSONDecodeError, KeyError):
                    pass

    t = threading.Thread(target=_read_stderr, daemon=True)
    t.start()

    stdout_data = proc.stdout.read()
    proc.wait()
    t.join(timeout=2.0)
    _current_proc = None

    if proc.returncode != 0:
        raise RuntimeError("WhisperX worker error:\n" + "\n".join(stderr_lines))

    data = _json.loads(stdout_data.decode("utf-8", errors="replace"))
    if "error" in data:
        raise RuntimeError(f"WhisperX: {data['error']}")

    transcription = data["transcription"]
    print(f"✅ Transcription WhisperX terminée ({len(transcription)} caractères)")
    return transcription
```

- [ ] **Étape 3 : Vérifier que l'import module ne casse pas**

```
D:\Utilitaires\Python\python.exe -c "import sys; sys.path.insert(0,'src'); import process; print('OK')"
```

Attendu : `OK`

- [ ] **Étape 4 : Vérifier les tests existants**

```
D:\Utilitaires\Python\python.exe -m pytest tests/test_process.py -v
```

Attendu : 7 tests PASSED

- [ ] **Étape 5 : Commit**

```bash
git add src/process.py
git commit -m "feat: refactor transcribe_whisperx to use Popen with real-time stderr thread"
```

---

### Task 5 : process.py — callbacks Whisper vanilla + _last_model_used

**Files:**
- Modify: `src/process.py`

- [ ] **Étape 1 : Mettre à jour la signature de transcribe_whisper**

Remplacer la ligne de définition :
```python
def transcribe_whisper(audio_path: str) -> str:
```
par :
```python
def transcribe_whisper(audio_path: str, on_progress=None) -> str:
```

- [ ] **Étape 2 : Ajouter les _emit dans transcribe_whisper**

Dans `transcribe_whisper`, après la ligne `print(f"   Device : {device.upper()}")`, ajouter :
```python
    _emit(on_progress, "transcription", 0.0, f"Chargement modèle {WHISPER_MODEL}...")
```

Dans le bloc `try:`, après `model = get_whisper_model()` et avant `audio = load_audio_numpy(...)`, ajouter :
```python
        _emit(on_progress, "transcription", 0.3, "Transcription en cours...")
```

Après `result = model.transcribe(...)` et avant `except Exception`, ajouter :
```python
        _emit(on_progress, "transcription", 1.0, "Transcription terminée")
```

- [ ] **Étape 3 : Mettre à jour la signature de transcribe**

Remplacer :
```python
def transcribe(audio_path: str) -> str:
    if USE_WHISPERX:
        return transcribe_whisperx(audio_path)
    return transcribe_whisper(audio_path)
```
par :
```python
def transcribe(audio_path: str, on_progress=None) -> str:
    if USE_WHISPERX:
        return transcribe_whisperx(audio_path, on_progress=on_progress)
    return transcribe_whisper(audio_path, on_progress=on_progress)
```

- [ ] **Étape 4 : Ajouter on_progress + _last_model_used à generate_report_from_text**

Remplacer la signature :
```python
def generate_report_from_text(transcription: str) -> str:
```
par :
```python
def generate_report_from_text(transcription: str, on_progress=None) -> str:
```

Au début de la fonction, après `print(f"\n📤 Génération du compte rendu via Gemini...")`, ajouter :
```python
    global _last_model_used
```

Dans la boucle `for api_key, model in attempts:`, ajouter en tout premier dans le corps de la boucle (avant `key_label = ...`) :
```python
        if _cancel_requested:
            raise ProcessCancelled("Traitement annulé par l'utilisateur")
```

Puis dans le bloc `try:`, juste avant `print(f"   Modèle : {model} [{key_label}]")`, ajouter :
```python
            _emit(on_progress, "gemini", -1.0, f"{model} [{key_label}]...")
```

Et juste avant `return response.text`, ajouter :
```python
            _last_model_used = f"{model} [{key_label}]"
```

- [ ] **Étape 5 : Vérifier les tests**

```
D:\Utilitaires\Python\python.exe -m pytest tests/test_process.py -v
```

Attendu : 7 tests PASSED

- [ ] **Étape 6 : Commit**

```bash
git add src/process.py
git commit -m "feat: add on_progress callbacks to Whisper vanilla and generate_report_from_text"
```

---

### Task 6 : Créer src/progress_window.py

**Files:**
- Create: `src/progress_window.py`

- [ ] **Étape 1 : Créer le fichier src/progress_window.py**

```python
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
import sys


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

    def lift(self) -> None:
        """Ramène la fenêtre au premier plan si elle existe encore."""
        if self._root:
            self._root.after(0, lambda: (self._root.lift(), self._root.focus_force()) if self._root else None)
```

- [ ] **Étape 2 : Vérifier l'import**

```
D:\Utilitaires\Python\python.exe -c "import sys; sys.path.insert(0,'src'); import progress_window; print('OK')"
```

Attendu : `OK`

- [ ] **Étape 3 : Test manuel rapide de la fenêtre**

```
D:\Utilitaires\Python\python.exe -c "
import sys; sys.path.insert(0,'src')
import threading, time
from process import ProgressEvent
from progress_window import ProgressWindow

win = ProgressWindow(on_cancel=lambda: print('cancel!'))
threading.Thread(target=win.mainloop, daemon=True).start()
time.sleep(0.5)
win.on_event(ProgressEvent('transcription', 0.3, 'Transcription en cours...'))
time.sleep(1)
win.on_event(ProgressEvent('gemini', -1.0, 'gemini-2.5-pro [perso]...'))
time.sleep(2)
win.on_event(ProgressEvent('done', 1.0, ''))
time.sleep(3)
"
```

Attendu : fenêtre apparaît, barre progresse, affiche "Terminé" et se ferme après 2 s.

- [ ] **Étape 4 : Commit**

```bash
git add src/progress_window.py
git commit -m "feat: add ProgressWindow tkinter floating window"
```

---

### Task 7 : tray.py — globaux, log append, tooltip dynamique, callback composite

**Files:**
- Modify: `src/tray.py`

- [ ] **Étape 1 : Changer tray.log de mode "w" à "a" avec horodatage de session**

Remplacer :
```python
sys.stderr = open(_log_path, "w", encoding="utf-8", buffering=1)
sys.stdout = sys.stderr
```
par :
```python
sys.stderr = open(_log_path, "a", encoding="utf-8", buffering=1)
sys.stdout = sys.stderr
sys.stderr.write(f"\n{'='*60}\n[session] {datetime.datetime.now().isoformat()}\n{'='*60}\n")
```

- [ ] **Étape 2 : Ajouter les imports manquants en tête de tray.py**

Après `import record` et `import process`, ajouter :
```python
import progress_window as pw
import time
```

- [ ] **Étape 3 : Ajouter les globaux de traitement**

Dans la section `# --- État global ---`, après les globaux existants (`_recording`, `_record_thread`, `_icon`), ajouter :
```python
_processing = False
_progress_win = None
_processing_start: float = 0.0
_meeting_duration_s: float = 0.0
```

- [ ] **Étape 4 : Ajouter la fonction _update_tray_tooltip**

Après la fonction `_set_state`, ajouter :
```python
def _update_tray_tooltip(event) -> None:
    if _icon is None:
        return
    _LABELS = {
        "transcription": "Transcription",
        "alignment": "Alignement",
        "diarization": "Diarisation",
        "gemini": "Génération CR",
    }
    label = _LABELS.get(event.step, event.step)
    detail = f"{label} {int(event.pct * 100)}%" if event.pct >= 0 else label
    if event.message:
        detail += f" · {event.message[:50]}"
    _icon.title = f"Meeting Recorder — {detail}"
```

- [ ] **Étape 5 : Mettre à jour process_async dans _stop**

Remplacer la fonction interne `process_async` (et son lancement) par la version suivante. Attention : ne pas toucher au code de `_stop` avant `def process_async():`.

```python
    def process_async():
        global _processing, _progress_win, _processing_start, _meeting_duration_s

        if not record.recording_chunks:
            print("[process] Aucun audio capturé")
            _set_state(icon, "idle", "Meeting Recorder")
            return

        _processing = True
        _processing_start = time.monotonic()
        process._reset_cancel()

        # Calcul de la durée de la réunion depuis les chunks enregistrés
        frames = sum(len(c) for c in record.recording_chunks)
        _meeting_duration_s = frames / record.SAMPLE_RATE

        # Fenêtre de progression
        win = pw.ProgressWindow(on_cancel=process.cancel)
        _progress_win = win
        threading.Thread(target=win.mainloop, daemon=True).start()

        def on_progress(event):
            if _progress_win is not None:
                _progress_win.on_event(event)
            _update_tray_tooltip(event)

        transcription_saved = False
        try:
            audio_path = record.save_recording()
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")

            _set_state(icon, "transcribing", "Meeting Recorder — Transcription en cours...")
            transcription = process.transcribe(audio_path, on_progress=on_progress)
            process.save_transcription(transcription, timestamp)
            transcription_saved = True

            _set_state(icon, "generating", "Meeting Recorder — Génération du CR...")
            report = process.generate_report_from_text(transcription, on_progress=on_progress)
            md_path = process.save_report(report, timestamp)

            on_progress(process.ProgressEvent(step="done", pct=1.0, message=""))

            elapsed = int(time.monotonic() - _processing_start)
            duration_min = _meeting_duration_s / 60
            model_label = process._last_model_used or "Gemini"
            _set_state(icon, "idle", "Meeting Recorder")
            _notify(
                "Compte rendu prêt ✓",
                f"Réunion : {duration_min:.0f} min · Traitement : {elapsed} s · {model_label}"
            )
            os.startfile(process.OUTPUT_DIR)

        except process.ProcessCancelled:
            if _progress_win is not None:
                _progress_win.on_event(process.ProgressEvent(step="done", pct=1.0, message=""))
            _set_state(icon, "idle", "Meeting Recorder")
            if transcription_saved:
                _notify("Traitement annulé", "transcription.txt conservée")
            else:
                _notify("Traitement annulé", "Aucun fichier sauvegardé")

        except Exception:
            traceback.print_exc()
            import io
            buf = io.StringIO()
            traceback.print_exc(file=buf)
            last_line = buf.getvalue().strip().split("\n")[-1]
            if _progress_win is not None:
                _progress_win.on_event(process.ProgressEvent(step="error", pct=-1.0, message=last_line))
            _set_state(icon, "idle", "Meeting Recorder — Erreur (voir tray.log)")
            _notify("Erreur Meeting Recorder", last_line[:120])

        finally:
            _processing = False
            _progress_win = None
            process._current_proc = None

    threading.Thread(target=process_async, daemon=True).start()
```

- [ ] **Étape 6 : Vérifier l'import du module tray (sans lancer l'UI)**

```
D:\Utilitaires\Python\python.exe -c "
import sys; sys.path.insert(0,'src')
# On ne peut pas importer tray directement car il redirige stderr
# Vérifier que process et progress_window s'importent correctement
import process, progress_window
print('imports OK')
"
```

Attendu : `imports OK`

- [ ] **Étape 7 : Commit**

```bash
git add src/tray.py
git commit -m "feat: add processing state, composite on_progress callback, dynamic tooltip, log append"
```

---

### Task 8 : tray.py — menu dynamique état Processing

**Files:**
- Modify: `src/tray.py`

- [ ] **Étape 1 : Ajouter les fonctions _cancel_processing et _show_progress_window**

Après la fonction `_quit`, ajouter :

```python
def _cancel_processing(icon, item):
    process.cancel()


def _show_progress_window(icon, item):
    global _progress_win
    if _progress_win is not None and _progress_win._root is not None:
        _progress_win.lift()
    elif _processing:
        win = pw.ProgressWindow(on_cancel=process.cancel)
        _progress_win = win
        threading.Thread(target=win.mainloop, daemon=True).start()
```

- [ ] **Étape 2 : Remplacer _build_menu() par la version avec état Processing**

Remplacer la totalité de `_build_menu()` par :

```python
def _build_menu():
    return pystray.Menu(
        pystray.MenuItem(
            lambda _: "Arrêter et générer le CR" if _recording else "Démarrer l'enregistrement",
            lambda icon, item: _stop(icon, item) if _recording else _start(icon, item),
            default=True,
            enabled=lambda _: not _processing,
        ),
        pystray.MenuItem(
            "Annuler le traitement",
            _cancel_processing,
            visible=lambda _: _processing,
        ),
        pystray.MenuItem(
            "Ouvrir la progression",
            _show_progress_window,
            visible=lambda _: _processing,
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            "Ouvrir le dossier des CR",
            lambda icon, item: os.startfile(process.OUTPUT_DIR),
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quitter", _quit),
    )
```

- [ ] **Étape 3 : Vérifier syntaxiquement**

```
D:\Utilitaires\Python\python.exe -m py_compile src/tray.py && echo "Syntaxe OK"
```

Attendu : `Syntaxe OK`

- [ ] **Étape 4 : Commit**

```bash
git add src/tray.py
git commit -m "feat: add Processing state menu (cancel + show progress)"
```

---

### Task 9 : Test d'intégration manuel end-to-end

**Files:** aucun fichier modifié — vérification uniquement

- [ ] **Étape 1 : Lancer l'application**

```
pythonw src\tray.py
```

Icône grise visible dans la barre des tâches.

- [ ] **Étape 2 : Démarrer un enregistrement de test (30 s)**

Clic droit → "Démarrer l'enregistrement". Parler 30 secondes. Clic droit → "Arrêter et générer le CR".

Vérifier :
- [ ] La fenêtre `ProgressWindow` apparaît automatiquement
- [ ] La barre de progression change d'état (transcription → alignement → génération)
- [ ] Le tooltip de l'icône se met à jour au survol
- [ ] Le menu affiche "Annuler le traitement" et "Ouvrir la progression" pendant le traitement
- [ ] "Démarrer l'enregistrement" est grisé pendant le traitement

- [ ] **Étape 3 : Vérifier la notification de succès**

Attendu : toast "Compte rendu prêt ✓" avec durée réunion, temps traitement, et modèle Gemini utilisé.

- [ ] **Étape 4 : Tester l'annulation**

Démarrer un second enregistrement, arrêter, puis cliquer "Annuler le traitement" pendant la transcription.

Vérifier :
- [ ] Toast "Traitement annulé — Aucun fichier sauvegardé" (si annulé avant save_transcription)
- [ ] Icône repasse en gris
- [ ] Tray.log contient `ProcessCancelled` ou l'entrée d'annulation

- [ ] **Étape 5 : Tester la fermeture manuelle de la fenêtre**

Démarrer un traitement, fermer la fenêtre avec la croix. Vérifier que le traitement continue (la notification de succès arrive quand même).

- [ ] **Étape 6 : Vérifier tray.log**

```
type tray.log
```

Vérifier :
- [ ] Le fichier contient plusieurs sessions avec horodatage `[session] 2026-...`
- [ ] Les sessions s'accumulent (mode append)

- [ ] **Étape 7 : Commit final**

```bash
git add .
git commit -m "feat: UX progression complete — ProgressWindow, cancel, enriched notifications"
```

---

## Self-review

**Couverture spec ↔ plan :**

| Exigence spec | Tâche |
|---|---|
| ProgressEvent dataclass | Task 1 |
| cancel() + ProcessCancelled | Task 2 |
| whisperx_worker stderr JSON | Task 3 |
| Popen + thread stderr | Task 4 |
| Vanilla callbacks + _last_model_used | Task 5 |
| ProgressWindow tkinter | Task 6 |
| Tooltip dynamique + log append | Task 7 |
| Menu Processing dynamique | Task 8 |
| Notifications enrichies + durée | Tasks 7+9 |
| "Ouvrir progression" recrée la fenêtre | Task 8 |
| Fermeture manuelle → traitement continue | Tasks 6+7 |
| Garder transcription.txt si annulé après save | Task 7 |

**Cohérence des types :**
- `ProgressEvent` défini Task 1, utilisé dans Tasks 2–9 ✓
- `on_progress: Optional[Callable[[ProgressEvent], None]]` partout ✓
- `win.on_event(event)` (pas `win.update`) utilisé partout ✓
- `process.cancel()` appelé depuis `ProgressWindow._do_cancel` et `_cancel_processing` ✓
- `_progress_win` global dans tray.py mis à jour dans `process_async` et `_show_progress_window` ✓
