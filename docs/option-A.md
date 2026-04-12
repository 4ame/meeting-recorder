# Option A — Python + Gemini (direct audio)

## Résumé

| Critère | Évaluation |
|---|---|
| Complexité setup | Moyenne |
| Fiabilité capture audio | ⚠️ Fragile (dépend du driver Windows) |
| Qualité compte rendu | Bonne |
| Coût | Gratuit (quota Gemini) |
| Dépendances | Python, clé API Gemini |

## Flux

```
Script Python (démarrage manuel)
        ↓
Capture micro + son système via WASAPI loopback
        ↓
Fichier .mp3 sauvegardé localement
        ↓
Envoi à l'API Gemini (audio + prompt)
        ↓
Fichier .md horodaté généré automatiquement
```

## Prérequis

- Python 3.10+
- Clé API Gemini active (console.cloud.google.com)
- Driver audio Windows avec Stereo Mix ou WASAPI loopback activé
- Packages Python : `soundcard`, `soundfile`, `google-generativeai`, `pydub`

## Installation

```bash
pip install soundcard soundfile google-generativeai pydub
```

Vérifier que le Stereo Mix est activé :
Panneau de configuration → Son → Enregistrement → clic droit → Afficher les appareils désactivés → Activer "Stereo Mix"

## Scripts

### record.py — Enregistrement audio

```python
import soundcard as sc
import soundfile as sf
import numpy as np
import threading
import datetime
import os

# --- Configuration ---
OUTPUT_DIR = "C:/recordings"
SAMPLE_RATE = 44100
CHANNELS = 2

recording = []
stop_event = threading.Event()

def record():
    """Capture le son système (loopback) et le micro en parallèle."""
    
    # Périphérique système (loopback)
    loopback = sc.get_microphone(id=str(sc.default_speaker().name), include_loopback=True)
    # Microphone par défaut
    mic = sc.default_microphone()

    with loopback.recorder(samplerate=SAMPLE_RATE, channels=CHANNELS) as lb_rec, \
         mic.recorder(samplerate=SAMPLE_RATE, channels=CHANNELS) as mic_rec:

        while not stop_event.is_set():
            # Capture 100ms de chaque source
            lb_data = lb_rec.record(numframes=int(SAMPLE_RATE * 0.1))
            mic_data = mic_rec.record(numframes=int(SAMPLE_RATE * 0.1))
            # Mix des deux flux (moyenne)
            mixed = (lb_data + mic_data) / 2
            recording.append(mixed)

def start():
    """Démarre l'enregistrement dans un thread séparé."""
    stop_event.clear()
    t = threading.Thread(target=record)
    t.start()
    print("⏺  Enregistrement démarré. Appuyez sur Entrée pour arrêter.")
    input()
    stop_event.set()
    t.join()
    save()

def save():
    """Sauvegarde le fichier .mp3 horodaté."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"{OUTPUT_DIR}/reunion_{timestamp}.mp3"
    
    audio_data = np.concatenate(recording, axis=0)
    sf.write(filename, audio_data, SAMPLE_RATE)
    print(f"✅ Fichier sauvegardé : {filename}")
    
    # Lancer automatiquement le traitement
    import process
    process.run(filename)

if __name__ == "__main__":
    start()
```

### process.py — Envoi à Gemini et génération du compte rendu

```python
import google.generativeai as genai
import datetime
import os

# --- Configuration ---
API_KEY = "VOTRE_CLE_API_GEMINI"  # ⚠️ À remplacer ou charger depuis .env
OUTPUT_DIR = "C:/recordings"
PROMPT_SYSTEM = """
[Coller ici le contenu du skill compte-rendu-reunion-it]
"""

genai.configure(api_key=API_KEY)

def run(audio_path: str):
    """Envoie l'audio à Gemini et sauvegarde le compte rendu."""
    
    print(f"📤 Envoi à Gemini : {audio_path}")
    
    # Vérifier la taille du fichier (limite 20MB inline)
    file_size = os.path.getsize(audio_path) / (1024 * 1024)
    
    if file_size > 20:
        # Utiliser File API pour les fichiers > 20MB
        print(f"📁 Fichier volumineux ({file_size:.1f}MB) — upload via File API")
        audio_file = genai.upload_file(audio_path, mime_type="audio/mp3")
        audio_part = audio_file
    else:
        # Envoi direct inline
        with open(audio_path, "rb") as f:
            audio_data = f.read()
        audio_part = {"mime_type": "audio/mp3", "data": audio_data}
    
    # Appel API Gemini
    model = genai.GenerativeModel("gemini-1.5-flash")
    response = model.generate_content([PROMPT_SYSTEM, audio_part])
    
    # Sauvegarde du compte rendu
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    output_path = f"{OUTPUT_DIR}/CR_{timestamp}.md"
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(response.text)
    
    print(f"✅ Compte rendu généré : {output_path}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        run(sys.argv[1])
```

## Déclenchement

Créer un fichier `start_recording.bat` :

```bat
@echo off
cd /d C:\recordings
python record.py
pause
```

Créer un raccourci sur le bureau pointant vers ce `.bat`.

## Points d'attention

- ⚠️ **Driver audio** : Stereo Mix absent sur certains PC — tester avant toute réunion
- ⚠️ **Taille fichier** : réunion > 1h dépasse 20MB → le script gère les deux cas
- 🔒 **Sécurité** : ne pas coder la clé API en dur — utiliser un fichier `.env`
- 🔄 **Reprise sur erreur** : si Gemini échoue, relancer `process.py reunion_xxx.mp3`

## Gestion sécurisée de la clé API

```bash
pip install python-dotenv
```

Créer un fichier `.env` dans le dossier :
```
GEMINI_API_KEY=votre_cle_ici
```

Dans `process.py`, remplacer la ligne API_KEY par :
```python
from dotenv import load_dotenv
load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")
```

## Estimation de mise en place

| Étape | Durée estimée |
|---|---|
| Installation Python + packages | 15 min |
| Activation Stereo Mix Windows | 10 min |
| Test de capture audio | 20 min |
| Configuration clé API Gemini | 10 min |
| Test complet sur une réunion | 30 min |
| **Total** | **~1h30** |
