# Option B — Whisper local + Gemini (hybride)

## Résumé

| Critère | Évaluation |
|---|---|
| Complexité setup | Moyenne |
| Fiabilité capture audio | ⚠️ Dépend du driver Windows (même que A) |
| Qualité transcription | ✅ Excellente (Whisper) |
| Qualité compte rendu | ✅ Très bonne |
| Coût | Gratuit |
| Dépendances | Python, Whisper, clé API Gemini |

## Différence vs Option A

Whisper transcrit l'audio localement **avant** d'envoyer à Gemini.
Gemini ne reçoit que du texte → plus rapide, plus fiable, pas de limite de taille.

## Flux

```
Script Python (démarrage manuel)
        ↓
Capture micro + son système → fichier .mp3
        ↓
Whisper local → transcription .txt
        ↓
Envoi du texte à l'API Gemini (+ prompt)
        ↓
Fichier .md horodaté généré automatiquement
```

## Prérequis

- Python 3.10+
- Clé API Gemini
- ffmpeg installé (requis par Whisper)
- GPU optionnel (CPU fonctionne, plus lent)
- Packages : `soundcard`, `soundfile`, `openai-whisper`, `google-generativeai`

## Installation

```bash
# 1. Installer ffmpeg (nécessaire pour Whisper)
# Télécharger sur https://ffmpeg.org/download.html
# Ajouter ffmpeg au PATH Windows

# 2. Installer les packages Python
pip install soundcard soundfile openai-whisper google-generativeai pydub

# 3. Télécharger le modèle Whisper (à faire une seule fois)
# Modèles disponibles : tiny, base, small, medium, large
# Recommandé : "small" (bon équilibre vitesse/qualité, ~460MB)
# Pour réunions multi-locuteurs : "medium" (~1.5GB)
python -c "import whisper; whisper.load_model('small')"
```

## Scripts

### record.py — Enregistrement audio (identique Option A)

```python
import soundcard as sc
import soundfile as sf
import numpy as np
import threading
import datetime
import os

OUTPUT_DIR = "C:/recordings"
SAMPLE_RATE = 44100
CHANNELS = 2

recording = []
stop_event = threading.Event()

def record():
    loopback = sc.get_microphone(id=str(sc.default_speaker().name), include_loopback=True)
    mic = sc.default_microphone()

    with loopback.recorder(samplerate=SAMPLE_RATE, channels=CHANNELS) as lb_rec, \
         mic.recorder(samplerate=SAMPLE_RATE, channels=CHANNELS) as mic_rec:

        while not stop_event.is_set():
            lb_data = lb_rec.record(numframes=int(SAMPLE_RATE * 0.1))
            mic_data = mic_rec.record(numframes=int(SAMPLE_RATE * 0.1))
            mixed = (lb_data + mic_data) / 2
            recording.append(mixed)

def start():
    stop_event.clear()
    t = threading.Thread(target=record)
    t.start()
    print("⏺  Enregistrement démarré. Appuyez sur Entrée pour arrêter.")
    input()
    stop_event.set()
    t.join()
    save()

def save():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"{OUTPUT_DIR}/reunion_{timestamp}.mp3"
    audio_data = np.concatenate(recording, axis=0)
    sf.write(filename, audio_data, SAMPLE_RATE)
    print(f"✅ Audio sauvegardé : {filename}")
    
    import process
    process.run(filename)

if __name__ == "__main__":
    start()
```

### process.py — Transcription Whisper + Compte rendu Gemini

```python
import whisper
import google.generativeai as genai
import datetime
import os
from dotenv import load_dotenv

# --- Configuration ---
load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")
OUTPUT_DIR = "C:/recordings"
WHISPER_MODEL = "small"  # tiny | base | small | medium | large
PROMPT_SYSTEM = """
[Coller ici le contenu du skill compte-rendu-reunion-it]
"""

genai.configure(api_key=API_KEY)

def transcribe(audio_path: str) -> str:
    """Transcrit l'audio avec Whisper en local."""
    print(f"🎙️  Transcription en cours (modèle : {WHISPER_MODEL})...")
    
    model = whisper.load_model(WHISPER_MODEL)
    result = model.transcribe(audio_path, language="fr", verbose=False)
    
    # Sauvegarder la transcription brute
    txt_path = audio_path.replace(".mp3", "_transcription.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(result["text"])
    
    print(f"✅ Transcription sauvegardée : {txt_path}")
    return result["text"]

def generate_report(transcription: str, timestamp: str):
    """Envoie la transcription à Gemini pour générer le compte rendu."""
    print("📤 Génération du compte rendu via Gemini...")
    
    model = genai.GenerativeModel("gemini-1.5-flash")
    
    # Gemini reçoit uniquement du texte → rapide et sans limite de taille
    prompt = f"{PROMPT_SYSTEM}\n\n## Transcription de la réunion\n\n{transcription}"
    response = model.generate_content(prompt)
    
    output_path = f"{OUTPUT_DIR}/CR_{timestamp}.md"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(response.text)
    
    print(f"✅ Compte rendu généré : {output_path}")

def run(audio_path: str):
    """Pipeline complet : transcription + compte rendu."""
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    
    # Étape 1 : transcription locale
    transcription = transcribe(audio_path)
    
    # Étape 2 : compte rendu via Gemini
    generate_report(transcription, timestamp)

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        run(sys.argv[1])
```

## Choix du modèle Whisper

| Modèle | Taille | Vitesse (CPU) | Qualité | Recommandé pour |
|---|---|---|---|---|
| tiny | 75MB | Très rapide | Basique | Tests rapides |
| base | 145MB | Rapide | Correcte | Réunions courtes, 1 locuteur |
| small | 460MB | Moyenne | Bonne | **Usage quotidien** |
| medium | 1.5GB | Lente | Très bonne | Multi-locuteurs, accents |
| large | 3GB | Très lente | Excellente | Nécessite GPU |

## Points d'attention

- ⚠️ **Première transcription lente** : le modèle se charge en mémoire (~30s)
- ⚠️ **CPU vs GPU** : sans GPU, une réunion d'1h prend ~10-15min à transcrire avec `small`
- ✅ **Pas de limite de taille** : Gemini reçoit du texte, pas de l'audio
- ✅ **Transcription archivée** : le `.txt` est conservé pour référence
- 🔒 **Tout reste local** : l'audio ne quitte jamais la machine

## Estimation de mise en place

| Étape | Durée estimée |
|---|---|
| Installation ffmpeg + packages | 20 min |
| Téléchargement modèle Whisper | 5-15 min |
| Test transcription sur fichier court | 20 min |
| Configuration clé API Gemini | 10 min |
| Test complet sur une réunion | 30 min |
| **Total** | **~1h30** |
