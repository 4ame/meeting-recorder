"""
watcher.py — Surveillance automatique d'un dossier (Options C et D)

Surveille un dossier et déclenche automatiquement le pipeline
de traitement dès qu'un nouveau fichier audio y est déposé.

Usage :
    python src/watcher.py                      # Démarre la surveillance
    python src/watcher.py --dir C:/mon/dossier # Dossier personnalisé
"""

import time
import os
import sys
import argparse
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from dotenv import load_dotenv

load_dotenv()

# --- Configuration ---
WATCH_DIR = os.getenv(
    "RECORDINGS_DIR",
    os.path.expanduser("~/Documents/Recordings")
)
AUDIO_EXTENSIONS = {'.mp3', '.m4a', '.wav', '.ogg', '.flac'}
FILE_STABILITY_CHECKS = 3   # Nombre de vérifications de stabilité
FILE_STABILITY_INTERVAL = 2 # Secondes entre chaque vérification


class AudioFileHandler(FileSystemEventHandler):
    """
    Détecte les nouveaux fichiers audio et déclenche le pipeline.
    Attend que l'écriture soit terminée avant de traiter.
    """

    def on_created(self, event):
        if event.is_directory:
            return

        path = event.src_path
        ext = Path(path).suffix.lower()

        if ext not in AUDIO_EXTENSIONS:
            return

        print(f"\n🆕 Nouveau fichier détecté : {os.path.basename(path)}")
        self._process_when_ready(path)

    def _process_when_ready(self, path: str):
        """Attend que le fichier soit stable puis lance le traitement."""
        if not self._wait_for_stability(path):
            print(f"⚠️  Fichier instable après attente — traitement annulé : {path}")
            return

        print(f"✅ Fichier prêt — démarrage du traitement")
        self._run_pipeline(path)

    def _wait_for_stability(self, path: str, timeout: int = 60) -> bool:
        """
        Vérifie que la taille du fichier ne change plus
        (indicateur que l'écriture est terminée).
        """
        print("⏳ Attente fin d'écriture...")
        stable_count = 0
        last_size = -1

        for _ in range(timeout):
            time.sleep(FILE_STABILITY_INTERVAL)

            try:
                current_size = os.path.getsize(path)
            except OSError:
                continue  # Fichier temporairement inaccessible

            if current_size == last_size and current_size > 0:
                stable_count += 1
                if stable_count >= FILE_STABILITY_CHECKS:
                    return True
            else:
                stable_count = 0
                last_size = current_size

        return False

    def _run_pipeline(self, path: str):
        """Lance le pipeline de traitement dans le process courant."""
        # Import ici pour éviter les dépendances circulaires
        sys.path.insert(0, str(Path(__file__).parent))
        import process
        process.run(path)


def start(watch_dir: str = None):
    """Démarre la surveillance du dossier."""
    target_dir = watch_dir or WATCH_DIR
    os.makedirs(target_dir, exist_ok=True)

    print(f"\n{'='*50}")
    print(f"👁️  Surveillance active")
    print(f"{'='*50}")
    print(f"📂 Dossier surveillé : {target_dir}")
    print(f"🎵 Extensions : {', '.join(AUDIO_EXTENSIONS)}")
    print(f"\nEn attente de nouveaux enregistrements...")
    print(f"(Ctrl+C pour arrêter)\n")

    event_handler = AudioFileHandler()
    observer = Observer()
    observer.schedule(event_handler, target_dir, recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n⏹  Surveillance arrêtée")
        observer.stop()

    observer.join()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Surveillance dossier audio")
    parser.add_argument("--dir", type=str, help="Dossier à surveiller")
    args = parser.parse_args()

    start(args.dir)
