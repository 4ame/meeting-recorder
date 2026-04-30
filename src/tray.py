"""
tray.py — Icône dans la barre des tâches pour contrôler l'enregistrement

Démarrer : double-clic sur lancer_enregistrement.bat
Contrôle  : clic droit sur l'icône → Démarrer / Arrêter / Quitter
"""

import sys
import os
import io
import threading
import traceback
import datetime

# Log des erreurs dans un fichier (pythonw n'affiche pas les erreurs)
_log_path = os.path.join(os.path.dirname(__file__), "..", "tray.log")
sys.stderr = open(_log_path, "a", encoding="utf-8", buffering=1)
sys.stdout = sys.stderr
sys.stderr.write(f"\n{'='*60}\n[session] {datetime.datetime.now().isoformat()}\n{'='*60}\n")

sys.path.insert(0, os.path.dirname(__file__))

import pystray
from PIL import Image, ImageDraw
import subprocess
import record
import process
import progress_window as pw
import time

# --- État global ---
_recording = False
_record_thread = None
_icon = None
_processing: bool = False
_progress_win = None
_processing_start: float = 0.0
_meeting_duration_s: float = 0.0

_COLORS = {
    "idle":         (120, 120, 120),  # gris
    "recording":    (210,  40,  40),  # rouge
    "transcribing": (220, 180,   0),  # jaune
    "generating":   ( 30, 120, 210),  # bleu
}

_TOOLTIP_LABELS = {
    "transcription": "Transcription",
    "alignment": "Alignement",
    "diarization": "Diarisation",
    "gemini": "Génération CR",
}


def _make_icon(state: str) -> Image.Image:
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([4, 4, 60, 60], fill=_COLORS[state])
    return img


def _set_state(icon, state: str, title: str):
    icon.icon = _make_icon(state)
    icon.title = title
    print(f"[état] {state} — {title}")


def _update_tray_tooltip(event) -> None:
    if _icon is None:
        return
    label = _TOOLTIP_LABELS.get(event.step, event.step)
    detail = f"{label} {int(event.pct * 100)}%" if event.pct >= 0 else label
    if event.message:
        detail += f" · {event.message[:50]}"
    _icon.title = f"Meeting Recorder — {detail}"


def _notify(title: str, message: str):
    try:
        xml_content = (
            f'<toast><visual><binding template="ToastText02">'
            f'<text id="1">{title}</text>'
            f'<text id="2">{message}</text>'
            f'</binding></visual></toast>'
        )
        script = (
            "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime] | Out-Null\n"
            "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType=WindowsRuntime] | Out-Null\n"
            "$xml = New-Object Windows.Data.Xml.Dom.XmlDocument\n"
            f"$xml.LoadXml('{xml_content}')\n"
            "$toast = [Windows.UI.Notifications.ToastNotification]::new($xml)\n"
            "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Meeting Recorder').Show($toast)\n"
        )
        subprocess.Popen(
            ["powershell", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-Command", script],
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except Exception as e:
        print(f"[notif] échec : {e}")


def _start(icon, item):
    global _recording, _record_thread
    if _recording:
        return
    _recording = True
    record.recording_chunks.clear()
    record.stop_event.clear()
    _set_state(icon, "recording", "Meeting Recorder — Enregistrement en cours...")
    _record_thread = threading.Thread(target=record.record_audio, daemon=True)
    _record_thread.start()


def _stop(icon, item):
    global _recording
    if not _recording:
        return
    _recording = False
    record.stop_event.set()
    if _record_thread:
        _record_thread.join()

    def process_async():
        global _processing, _progress_win, _processing_start, _meeting_duration_s

        if not record.recording_chunks:
            print("[process] Aucun audio capturé")
            _set_state(icon, "idle", "Meeting Recorder")
            return

        _processing = True
        _processing_start = time.monotonic()
        process._reset_cancel()

        frames = sum(len(c) for c in record.recording_chunks)
        _meeting_duration_s = frames / record.SAMPLE_RATE

        win = pw.ProgressWindow(on_cancel=process.cancel)
        _progress_win = win
        threading.Thread(target=win.mainloop, daemon=True).start()

        def on_progress(event):
            win.on_event(event)
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
            buf = io.StringIO()
            traceback.print_exc(file=buf)
            tb_text = buf.getvalue()
            sys.stderr.write(tb_text)
            last_line = tb_text.strip().split("\n")[-1]
            win.on_event(process.ProgressEvent(step="error", pct=-1.0, message=last_line))
            _set_state(icon, "idle", "Meeting Recorder — Erreur (voir tray.log)")
            _notify("Erreur Meeting Recorder", last_line[:120])

        finally:
            _processing = False
            _progress_win = None
            process._current_proc = None

    threading.Thread(target=process_async, daemon=True).start()


def _quit(icon, item):
    if _recording:
        record.stop_event.set()
    icon.stop()


def _cancel_processing(icon, item):
    process.cancel()


def _show_progress_window(icon, item):
    global _progress_win
    current = _progress_win  # snapshot atomique — _progress_win peut être mis à None par process_async
    if current is not None and current.is_alive:
        current.lift()
    elif _processing:
        new_win = pw.ProgressWindow(on_cancel=process.cancel)
        _progress_win = new_win
        threading.Thread(target=new_win.mainloop, daemon=True).start()


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


if __name__ == "__main__":
    try:
        print("Démarrage Meeting Recorder...")
        _icon = pystray.Icon(
            name="meeting-recorder",
            icon=_make_icon("idle"),
            title="Meeting Recorder",
            menu=_build_menu(),
        )
        print("Icône créée, lancement de la boucle...")
        _icon.run()
    except Exception:
        traceback.print_exc()
