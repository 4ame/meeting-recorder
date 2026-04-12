# Meeting Recorder

Pipeline automatisé : enregistrement audio réunion → transcription → compte rendu IT.

## Prérequis

- Python 3.10+
- ffmpeg installé et dans le PATH ([ffmpeg.org](https://ffmpeg.org/download.html))
- Clé API Gemini ([console.cloud.google.com](https://console.cloud.google.com))

## Installation

```bash
# 1. Cloner le projet
git clone <repo> meeting-recorder
cd meeting-recorder

# 2. Installer les dépendances
pip install -r requirements.txt

# 3. Configurer l'environnement
cp .env.example .env
# Éditer .env et renseigner GEMINI_API_KEY

# 4. Télécharger le modèle Whisper (une seule fois, ~460MB)
python -c "import whisper; whisper.load_model('small')"
```

## Usage rapide

```bash
# Option A/B — Enregistrement direct
python src/record.py

# Option C/D — Surveillance automatique d'un dossier
python src/watcher.py

# Traitement d'un fichier existant
python src/process.py recordings/ma_reunion.mp3
```

## Options d'implémentation

Voir `docs/options.md` pour le comparatif complet des 4 approches.

| Option | Capture | Recommandée si |
|---|---|---|
| A | Python (WASAPI) | Setup minimal souhaité |
| B | Python + Whisper | Meilleure qualité transcription |
| C | OBS + Whisper | Driver Stereo Mix absent |
| **D** | **Windows + Whisper** | **Démarrage recommandé** |

## Structure des sorties

```
~/Documents/
├── Recordings/          ← enregistrements audio
└── CompteRendus/
    ├── transcription_YYYYMMDD_HHMM.txt
    └── CR_YYYYMMDD_HHMM.md
```
