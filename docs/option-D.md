# Option D — Enregistreur Windows + Whisper + Gemini ⭐ Recommandée

## Résumé

| Critère | Évaluation |
|---|---|
| Complexité setup | ✅ Faible |
| Fiabilité capture audio | ✅ Bonne (délégué à Windows) |
| Qualité transcription | ✅ Excellente (Whisper) |
| Qualité compte rendu | ✅ Très bonne |
| Coût | Gratuit |
| Dépendances | Python, Whisper, clé API Gemini |

## Pourquoi c'est l'option recommandée

- **Aucun code de capture audio** — Windows gère la partie la plus fragile
- **Script Python minimal** — uniquement transcription + compte rendu
- **Le plus maintenable** sur la durée
- **Fallback naturel** : si la capture Windows pose problème → basculer sur Option C (OBS)

## Flux

```
Enregistreur Windows (raccourci clavier)
        ↓
Fichier audio sauvegardé dans un dossier surveillé
        ↓
Script Python (watchdog détecte le nouveau fichier)
        ↓
Whisper local → transcription .txt
        ↓
API Gemini → compte rendu .md
```

## Prérequis

- Windows 10/11 avec l'application **Enregistreur vocal** (pré-installée)
- Python 3.10+
- Clé API Gemini
- ffmpeg
- Packages : `openai-whisper`, `google-generativeai`, `watchdog`, `python-dotenv`

## ⚠️ Limite connue

L'enregistreur vocal Windows capture le **microphone uniquement** par défaut.
Pour capturer aussi le son du PC (interlocuteurs en visio), deux options :
- **Option 1** : activer "Stereo Mix" dans les paramètres son Windows (si disponible)
- **Option 2** : utiliser un câble audio virtuel (VB-Cable, gratuit) qui route le son système vers un micro virtuel

## Installation

### 1. Vérifier l'Enregistreur vocal Windows

Rechercher "Enregistreur vocal" dans le menu Démarrer.
Sur Windows 11 : l'application s'appelle "Sound Recorder".

Configurer le dossier de sauvegarde :
`%USERPROFILE%\Documents\Recordings\`

### 2. VB-Cable (optionnel, pour capturer le son système)

Télécharger sur : https://vb-audio.com/Cable/
Installer → redémarrer → dans les paramètres son Windows, sélectionner VB-Cable comme entrée micro dans l'Enregistreur vocal.

### 3. Packages Python

```bash
pip install openai-whisper google-generativeai watchdog python-dotenv
```

### 4. Modèle Whisper (une seule fois)

```bash
python -c "import whisper; whisper.load_model('small')"
```

## Scripts

### watcher.py — Surveillance + pipeline complet

```python
import time
import os
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import whisper
import google.generativeai as genai
import datetime
from dotenv import load_dotenv

# --- Configuration ---
load_dotenv()
WATCH_DIR = os.path.expanduser("~/Documents/Recordings")
OUTPUT_DIR = os.path.expanduser("~/Documents/CompteRendus")
WHISPER_MODEL = "small"
API_KEY = os.getenv("GEMINI_API_KEY")

PROMPT_SYSTEM = """
[Coller ici le contenu du skill compte-rendu-reunion-it]
"""

genai.configure(api_key=API_KEY)

def transcribe(audio_path: str) -> str:
    """Transcription locale avec Whisper."""
    print(f"🎙️  Transcription : {os.path.basename(audio_path)}")
    model = whisper.load_model(WHISPER_MODEL)
    result = model.transcribe(audio_path, language="fr", verbose=False)
    print(f"✅ Transcription terminée ({len(result['text'])} caractères)")
    return result["text"]

def generate_report(transcription: str) -> str:
    """Génère le compte rendu via Gemini."""
    print("📤 Génération du compte rendu...")
    model = genai.GenerativeModel("gemini-1.5-flash")
    prompt = f"{PROMPT_SYSTEM}\n\n## Transcription de la réunion\n\n{transcription}"
    response = model.generate_content(prompt)
    print("✅ Compte rendu généré")
    return response.text

def process(audio_path: str):
    """Pipeline complet : transcription → compte rendu → sauvegarde."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    
    try:
        # Transcription
        transcription = transcribe(audio_path)
        
        # Sauvegarde transcription brute
        txt_path = os.path.join(OUTPUT_DIR, f"transcription_{timestamp}.txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(transcription)
        
        # Compte rendu
        report = generate_report(transcription)
        
        # Sauvegarde compte rendu
        md_path = os.path.join(OUTPUT_DIR, f"CR_{timestamp}.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(report)
        
        print(f"\n🎉 Terminé !")
        print(f"   Transcription : {txt_path}")
        print(f"   Compte rendu  : {md_path}")
        
    except Exception as e:
        # Sauvegarde de l'erreur pour diagnostic
        error_path = os.path.join(OUTPUT_DIR, f"erreur_{timestamp}.txt")
        with open(error_path, "w") as f:
            f.write(f"Erreur lors du traitement de {audio_path}\n{str(e)}")
        print(f"❌ Erreur : {e} — détails dans {error_path}")

class AudioHandler(FileSystemEventHandler):
    """Détecte les nouveaux fichiers audio et déclenche le traitement."""
    
    def on_created(self, event):
        if event.is_directory:
            return
        
        ext = os.path.splitext(event.src_path)[1].lower()
        if ext not in ('.mp3', '.m4a', '.wav', '.ogg'):
            return
        
        print(f"\n🆕 Nouveau fichier : {os.path.basename(event.src_path)}")
        
        # Attendre que l'écriture soit complète
        self._wait_for_file(event.src_path)
        process(event.src_path)
    
    def _wait_for_file(self, path: str, timeout: int = 30):
        """Attend que le fichier soit stable (écriture terminée)."""
        print("⏳ Attente fin d'écriture...")
        for _ in range(timeout):
            time.sleep(1)
            try:
                size1 = os.path.getsize(path)
                time.sleep(1)
                size2 = os.path.getsize(path)
                if size1 == size2 and size1 > 0:
                    return
            except OSError:
                continue
        print("⚠️  Timeout — démarrage quand même")

def start():
    os.makedirs(WATCH_DIR, exist_ok=True)
    
    event_handler = AudioHandler()
    observer = Observer()
    observer.schedule(event_handler, WATCH_DIR, recursive=False)
    observer.start()
    
    print(f"👁️  Surveillance active : {WATCH_DIR}")
    print(f"📁 Comptes rendus → {OUTPUT_DIR}")
    print("En attente d'enregistrements...\n")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

if __name__ == "__main__":
    start()
```

## Fichier .env

Créer `C:\recordings\.env` :
```
GEMINI_API_KEY=votre_cle_ici
```

## Démarrage automatique du watcher

Créer `start_watcher.bat` :
```bat
@echo off
cd /d %USERPROFILE%\Documents
python watcher.py
```

Ajouter dans le démarrage Windows :
`Win+R` → `shell:startup` → copier le `.bat`

## Usage quotidien

1. `watcher.py` tourne en arrière-plan (démarrage automatique)
2. Début de réunion → ouvrir **Enregistreur vocal** → ⏺
3. Fin de réunion → ⏹
4. Le compte rendu apparaît dans `Documents/CompteRendus/` automatiquement

## Structure des fichiers générés

```
Documents/
├── Recordings/          ← dossier surveillé (enregistreur Windows)
│   └── reunion_xxx.m4a
└── CompteRendus/        ← sortie automatique
    ├── transcription_20250615_1430.txt
    └── CR_20250615_1430.md
```

## Points d'attention

- ⚠️ **Son système** : nécessite VB-Cable ou Stereo Mix pour capter les interlocuteurs
- ✅ **Capture micro native** : fonctionne sans configuration supplémentaire
- ✅ **Reprise sur erreur** : les erreurs sont loguées, l'audio est conservé
- ✅ **Le plus simple à maintenir** des 4 options
- 💡 **Si VB-Cable pose problème** → basculer sur Option C (OBS)

## Estimation de mise en place

| Étape | Durée estimée |
|---|---|
| Vérification Enregistreur vocal | 5 min |
| Installation VB-Cable (optionnel) | 15 min |
| Installation Python + packages + ffmpeg | 20 min |
| Configuration .env + test API Gemini | 10 min |
| Test transcription Whisper | 15 min |
| Test pipeline complet | 20 min |
| **Total** | **~1h à 1h30** |
