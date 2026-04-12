# Option C — OBS Studio + Whisper + Gemini

## Résumé

| Critère | Évaluation |
|---|---|
| Complexité setup | Élevée (OBS à configurer) |
| Fiabilité capture audio | ✅ Très élevée (OBS battle-tested) |
| Qualité transcription | ✅ Excellente (Whisper) |
| Qualité compte rendu | ✅ Très bonne |
| Coût | Gratuit |
| Dépendances | OBS Studio, Python, Whisper, clé API Gemini |

## Quand choisir cette option

Choisir Option C si :
- L'Option A ou B échoue sur la capture audio (driver Stereo Mix absent)
- Tu veux une capture audio robuste et professionnelle
- Tu utilises déjà OBS pour d'autres usages

## Flux

```
OBS Studio (capture micro + son système)
        ↓
Raccourci clavier → Start/Stop enregistrement
        ↓
Fichier .mp3 déposé automatiquement dans un dossier surveillé
        ↓
Script Python (watchdog détecte le nouveau fichier)
        ↓
Whisper local → transcription .txt
        ↓
API Gemini → compte rendu .md
```

## Prérequis

- OBS Studio (https://obsproject.com/) — gratuit
- Python 3.10+
- Clé API Gemini
- ffmpeg
- Packages : `openai-whisper`, `google-generativeai`, `watchdog`

## Installation

```bash
pip install openai-whisper google-generativeai watchdog python-dotenv
```

## Configuration OBS Studio

### Étape 1 — Sources audio

Dans OBS → Sources → Ajouter :
- **Capture audio (sortie)** → capte le son du PC (Teams, Zoom, Meet)
- **Capture audio (entrée)** → capte ton microphone

### Étape 2 — Format d'enregistrement

Paramètres → Sortie → Enregistrement :
- Format : **mp3** ou **m4a**
- Dossier : `C:\recordings\raw\`
- Qualité : 128 kbps (suffisant pour transcription)

### Étape 3 — Raccourcis clavier

Paramètres → Raccourcis :
- Démarrer l'enregistrement : `Ctrl+Shift+R`
- Arrêter l'enregistrement : `Ctrl+Shift+S`

### Étape 4 — Démarrage automatique avec Windows (optionnel)

Créer un raccourci OBS dans le dossier Démarrage Windows :
`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup`

## Scripts

### watcher.py — Surveillance du dossier et traitement automatique

```python
import time
import os
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import process

WATCH_DIR = "C:/recordings/raw"

class AudioHandler(FileSystemEventHandler):
    """Déclenche le traitement dès qu'un nouveau fichier audio apparaît."""
    
    def on_created(self, event):
        if event.is_directory:
            return
        
        # Filtrer uniquement les fichiers audio
        if not event.src_path.endswith(('.mp3', '.m4a', '.wav')):
            return
        
        print(f"🆕 Nouveau fichier détecté : {event.src_path}")
        
        # Attendre que l'écriture soit terminée (OBS peut prendre quelques secondes)
        time.sleep(3)
        
        # Vérifier que le fichier est stable (taille ne change plus)
        size_before = os.path.getsize(event.src_path)
        time.sleep(2)
        size_after = os.path.getsize(event.src_path)
        
        if size_before == size_after:
            print("✅ Fichier stable — démarrage du traitement")
            process.run(event.src_path)
        else:
            print("⏳ Fichier encore en cours d'écriture — nouvelle vérification dans 5s")
            time.sleep(5)
            process.run(event.src_path)

def start():
    """Démarre la surveillance du dossier."""
    os.makedirs(WATCH_DIR, exist_ok=True)
    
    event_handler = AudioHandler()
    observer = Observer()
    observer.schedule(event_handler, WATCH_DIR, recursive=False)
    observer.start()
    
    print(f"👁️  Surveillance active : {WATCH_DIR}")
    print("En attente de nouveaux fichiers audio...")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    
    observer.join()

if __name__ == "__main__":
    start()
```

### process.py — Transcription + Compte rendu (identique Option B)

```python
import whisper
import google.generativeai as genai
import datetime
import os
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")
OUTPUT_DIR = "C:/recordings/reports"
WHISPER_MODEL = "small"
PROMPT_SYSTEM = """
[Coller ici le contenu du skill compte-rendu-reunion-it]
"""

genai.configure(api_key=API_KEY)

def transcribe(audio_path: str) -> str:
    print(f"🎙️  Transcription en cours...")
    model = whisper.load_model(WHISPER_MODEL)
    result = model.transcribe(audio_path, language="fr", verbose=False)
    
    txt_path = audio_path.replace(".mp3", "_transcription.txt").replace(".m4a", "_transcription.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(result["text"])
    
    print(f"✅ Transcription : {txt_path}")
    return result["text"]

def generate_report(transcription: str, timestamp: str):
    print("📤 Génération du compte rendu...")
    model = genai.GenerativeModel("gemini-1.5-flash")
    prompt = f"{PROMPT_SYSTEM}\n\n## Transcription\n\n{transcription}"
    response = model.generate_content(prompt)
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = f"{OUTPUT_DIR}/CR_{timestamp}.md"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(response.text)
    
    print(f"✅ Compte rendu : {output_path}")

def run(audio_path: str):
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    transcription = transcribe(audio_path)
    generate_report(transcription, timestamp)

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        run(sys.argv[1])
```

## Démarrage du watcher au démarrage Windows

Créer `start_watcher.bat` :
```bat
@echo off
cd /d C:\recordings
python watcher.py
```

Ajouter ce `.bat` dans :
`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup`

## Usage quotidien

1. OBS démarre automatiquement avec Windows
2. Début de réunion → `Ctrl+Shift+R`
3. Fin de réunion → `Ctrl+Shift+S`
4. Le compte rendu `.md` apparaît dans `C:\recordings\reports\` automatiquement

## Points d'attention

- ⚠️ **OBS doit tourner** en arrière-plan pendant les réunions
- ⚠️ **watcher.py doit tourner** pour le traitement automatique
- ✅ **Capture audio la plus fiable** des 4 options
- ✅ **Zéro intervention manuelle** une fois configuré
- 💡 **OBS peut aussi enregistrer la vidéo** si besoin ultérieurement

## Estimation de mise en place

| Étape | Durée estimée |
|---|---|
| Installation OBS + configuration audio | 30 min |
| Configuration raccourcis + dossier sortie | 15 min |
| Installation Python + packages | 15 min |
| Test capture audio OBS | 20 min |
| Test pipeline complet | 30 min |
| **Total** | **~1h45** |
