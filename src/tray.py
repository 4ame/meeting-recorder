"""
tray.py — Icône dans la barre des tâches pour contrôler l'enregistrement

Démarrer : double-clic sur lancer_enregistrement.bat
Contrôle  : clic droit sur l'icône → Démarrer / Arrêter / Quitter
"""

import sys
import os
import threading
import traceback
import datetime

# Log des erreurs dans un fichier (pythonw n'affiche pas les erreurs)
_log_path = os.path.join(os.path.dirname(__file__), "..", "tray.log")
sys.stderr = open(_log_path, "w", encoding="utf-8", buffering=1)
sys.stdout = sys.stderr

sys.path.insert(0, os.path.dirname(__file__))

import pystray
from PIL import Image, ImageDraw
import subprocess
import record
import process

# --- État global ---
_recording = False
_record_thread = None
_icon = None

_COLORS = {
    "idle":         (120, 120, 120),  # gris
    "recording":    (210,  40,  40),  # rouge
    "transcribing": (220, 180,   0),  # jaune
    "generating":   ( 30, 120, 210),  # bleu
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
        try:
            if not record.recording_chunks:
                print("[process] Aucun audio capturé")
                _set_state(icon, "idle", "Meeting Recorder")
                return

            audio_path = record.save_recording()
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")

            _set_state(icon, "transcribing", "Meeting Recorder — Transcription en cours...")
            transcription = process.transcribe(audio_path)
            process.save_transcription(transcription, timestamp)

            _set_state(icon, "generating", "Meeting Recorder — Génération du CR...")
            report = process.generate_report_from_text(transcription)
            md_path = process.save_report(report, timestamp)

            _set_state(icon, "idle", "Meeting Recorder")
            _notify("Compte rendu prêt ✓", f"Fichier : {os.path.basename(md_path)}")
            os.startfile(process.OUTPUT_DIR)

        except Exception:
            traceback.print_exc()
            _set_state(icon, "idle", "Meeting Recorder — Erreur (voir tray.log)")
            _notify("Erreur Meeting Recorder", "Consulter tray.log pour les détails")

    threading.Thread(target=process_async, daemon=True).start()


def _quit(icon, item):
    if _recording:
        record.stop_event.set()
    icon.stop()


def _build_menu():
    return pystray.Menu(
        pystray.MenuItem(
            lambda _: "Arrêter et générer le CR" if _recording else "Démarrer l'enregistrement",
            lambda icon, item: _stop(icon, item) if _recording else _start(icon, item),
            default=True,
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Ouvrir le dossier des CR", lambda icon, item: os.startfile(process.OUTPUT_DIR)),
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
