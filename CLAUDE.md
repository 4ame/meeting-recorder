# Meeting Recorder — Workflow audio → compte rendu IT

## Vue d'ensemble

Pipeline Python (Windows) qui :
1. Enregistre l'audio d'une réunion (micro Bluetooth + son système via WASAPI loopback)
2. Transcrit localement via Whisper ou WhisperX (GPU CUDA)
3. Génère un compte rendu structuré via l'API Gemini

Interface : icône dans la barre des tâches (pystray). Zéro intervention manuelle après déclenchement.

## Stack technique

- **Python 3.14** (host, D:\Utilitaires\Python\) — environnement principal
- **Python 3.12** (venv-whisperx, via Scoop) — environnement isolé pour WhisperX
- **Whisper large-v3-turbo** (OpenAI, local, GPU) — transcription vanilla
- **WhisperX 3.8.5** (Python 3.12, venv dédié) — transcription avec alignement mot/temps + diarisation
- **pyannote.audio 4.0.4** — diarisation speaker (nécessite HF_TOKEN)
- **Gemini** (`gemini-2.5-pro` [clé perso] → `gemini-3.1-pro-preview` [clé entreprise] → `gemini-3-flash-preview` → `gemini-2.5-flash`) — génération CR, chaîne de fallback dans `generate_report_from_text()`
- **sounddevice** — capture micro (compatible Bluetooth/WASAPI PCM)
- **soundcard** — capture son système (WASAPI loopback)
- **pystray + Pillow** — icône barre des tâches
- **FFmpeg 8.1** (Scoop) — requis par WhisperX pour le chargement audio
- **PyTorch 2.8 CUDA 12.8** — GPU RTX 2080 (8 Go VRAM)

## Structure du projet

```
meeting-recorder/
├── CLAUDE.md                   ← ce fichier
├── .env                        ← secrets (ne jamais committer)
├── .env.example                ← template sans valeurs sensibles
├── .gitignore
├── requirements.txt            ← dépendances env principal (Python 3.14)
├── icon.ico                    ← icône micro pour le tray et le raccourci
├── creer_raccourci.ps1         ← crée un .lnk bureau vers tray.py (épinglable)
├── src/
│   ├── tray.py                 ← point d'entrée — icône tray + orchestration
│   ├── record.py               ← capture audio micro + système
│   ├── process.py              ← transcription Whisper/WhisperX + CR Gemini + ProgressEvent
│   ├── whisperx_worker.py      ← worker WhisperX (exécuté dans venv-whisperx)
│   ├── progress_window.py      ← fenêtre tkinter flottante de progression (thread-safe)
│   └── watcher.py              ← surveillance dossier (non utilisé en prod)
├── tests/
│   ├── conftest.py             ← ajoute src/ au sys.path pour pytest
│   └── test_process.py         ← tests unitaires : ProgressEvent, cancel(), _emit()
├── prompts/
│   └── compte-rendu.md         ← prompt système injecté dans Gemini (éditable)
├── docs/
│   ├── options.md
│   ├── option-A.md / B / C / D.md
├── venv-whisperx/              ← venv Python 3.12 pour WhisperX (ignoré par git)
├── recordings/                 ← fichiers audio WAV (ignorés par git)
└── output/                     ← non utilisé (sortie dans GeneratedCR/)
```

**Sortie réelle** : `~/Documents/GeneratedCR/CompteRendus/reunion_YYYYMMDD_HHMM/`
- `transcription.txt` — transcription brute
- `CR.md` — compte rendu Gemini

## Environnements Python

| Env | Interpréteur | Usage |
|-----|-------------|-------|
| Principal | `D:\Utilitaires\Python\python.exe` | tray, record, process |
| WhisperX | `venv-whisperx\Scripts\python.exe` | whisperx_worker.py uniquement |

Pour créer le venv WhisperX (si absent) :
```powershell
# Python 3.12 installé via Scoop
C:\Users\arnau\scoop\apps\python312\current\python.exe -m venv venv-whisperx
venv-whisperx\Scripts\pip install torch==2.8.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cu128
venv-whisperx\Scripts\pip install whisperx
# Réinstaller torch CUDA après whisperx (qui installe la version CPU)
venv-whisperx\Scripts\pip install torch==2.8.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cu128 --force-reinstall --no-deps
```

## Commandes essentielles

```powershell
# Lancer l'interface tray (point d'entrée principal)
pythonw src/tray.py

# Tester la capture audio
python src/record.py --test

# Traiter un fichier audio existant manuellement
python -X utf8 src/process.py recordings/reunion_xxx.wav

# Régénérer un CR depuis une transcription existante
python -X utf8 src/process.py --transcript path/to/transcription.txt

# Installer les dépendances (env principal)
pip install -r requirements.txt
```

> **Important** : toujours utiliser `-X utf8` pour les appels manuels à `process.py` afin d'éviter les UnicodeEncodeError sur les emojis (console Windows CP1252).

## Variables d'environnement (.env)

| Variable | Obligatoire | Description |
|----------|------------|-------------|
| `GEMINI_API_KEY` | ✅ | Clé API Google Gemini (compte perso) |
| `GEMINI_API_KEY_COMPANY` | Non | Clé API Google Gemini (compte entreprise) — active la chaîne de fallback étendue |
| `WHISPER_MODEL` | Non | Modèle Whisper (défaut : `large-v3-turbo`) |
| `USE_WHISPERX` | Non | `1` = WhisperX, `0` = Whisper vanilla (défaut : `0`) |
| `HF_TOKEN` | Non | Token HuggingFace pour la diarisation pyannote |
| `OUTPUT_DIR` | Non | Dossier de sortie des CR |
| `GEMINI_DEBUG` | Non | `1` = log détaillé des requêtes Gemini (tokens, traceback complet) |

## Règles de sécurité

- **Ne jamais committer `.env`** — contient `GEMINI_API_KEY` et `HF_TOKEN`
- **Ne jamais committer `venv-whisperx/`** — déjà dans `.gitignore`, ~4 Go
- Vérifier que `.env` est bien dans `.gitignore` avant chaque `git commit`
- `HF_TOKEN` donne accès aux modèles HuggingFace — traiter comme un mot de passe
- Les dossiers `recordings/` et `GeneratedCR/` contiennent des données audio de réunions — ne pas versionner

## Comportement attendu de Claude Code

### Avant tout commit
1. Vérifier que `.env`, `venv-whisperx/`, `recordings/`, `GeneratedCR/`, `tray.log` sont dans `.gitignore`
2. Ne jamais forcer l'ajout de ces fichiers

### Développement
- Toujours utiliser `-X utf8` dans les commandes Python impliquant des emojis ou du texte français
- Tester chaque composant isolément avant d'assembler : `record.py --test` → `process.py fichier.wav` → `tray.py`
- Le modèle Whisper est déchargé de la VRAM après chaque transcription (`unload_whisper_model()`) — ne pas modifier ce comportement
- `whisperx_worker.py` s'exécute toujours via `venv-whisperx\Scripts\python.exe`, jamais avec l'interpréteur principal
- Pour passer du JSON entre `process.py` et `whisperx_worker.py`, stdout du worker est réservé au JSON ; tous les logs vont sur stderr

### Si la capture audio échoue
- Micro Bluetooth : vérifier que sounddevice est utilisé (pas soundcard) — le Bluetooth n'expose pas WAVE_FORMAT_EXTENSIBLE
- Son système : vérifier que le périphérique de lecture Windows correspond au loopback soundcard
- Consulter `docs/option-D.md` pour le fallback VB-Cable

### Si CUDA échoue
- `process.py` bascule automatiquement sur CPU via le bloc `except` dans `transcribe_whisper()`
- Si le problème persiste, vérifier que PyTorch est bien la version CUDA : `python -c "import torch; print(torch.cuda.is_available())"`

### Prompt Gemini
- Le prompt est dans `prompts/compte-rendu.md` — modifiable sans toucher au code
- La chaîne de modèles (pro → flash) est dans `generate_report_from_text()` dans `process.py`

## Maintenance de la documentation

### Principe
Ce fichier `CLAUDE.md` est la **source de vérité** du projet. Il doit refléter l'état réel du code à tout moment. Claude Code est responsable de le maintenir à jour au fil des évolutions.

### Quand mettre à jour ce fichier

| Changement | Sections à mettre à jour |
|---|---|
| Nouveau fichier source dans `src/` | Structure du projet |
| Changement de modèle Whisper ou Gemini | Stack technique, Variables d'environnement |
| Nouvelle variable dans `.env` | Variables d'environnement + `.env.example` |
| Nouvelle dépendance | Stack technique, Environnements Python |
| Changement de comportement CUDA/fallback | Comportement attendu → Si CUDA échoue |
| Nouveau script utilitaire (`.ps1`, etc.) | Structure du projet, Commandes essentielles |
| Modification du pipeline principal | Vue d'ensemble, Commandes essentielles |
| Ajout d'une règle de sécurité | Règles de sécurité, `.gitignore` si nécessaire |

### Comment mettre à jour

1. **À chaque modification significative du code**, vérifier si l'une des sections ci-dessus est impactée
2. **Mettre à jour `CLAUDE.md` dans la même session** que la modification — ne pas différer
3. **Mettre à jour `.env.example`** si une nouvelle variable d'environnement est introduite
4. **Ne pas supprimer** les sections existantes sans raison — enrichir plutôt que remplacer
5. **Garder les commandes testées** : ne documenter que des commandes qui ont fonctionné

### Ce qu'il ne faut pas faire
- Ne pas laisser la stack technique pointer vers d'anciens modèles (ex. `gemini-1.5-flash`)
- Ne pas omettre un nouveau fichier source de la structure
- Ne pas documenter une variable `.env` sans l'ajouter également à `.env.example`
- Ne pas modifier `.gitignore` sans vérifier que `CLAUDE.md` reste cohérent avec les règles de sécurité

## Posture de développement expert

Claude Code doit se comporter comme un développeur senior sur ce projet. Cela implique une posture proactive : ne pas se contenter d'exécuter les demandes, mais analyser, signaler et proposer.

### Analyse systématique avant toute modification

Avant de modifier du code, toujours évaluer :
- **L'impact sur les autres composants** — un changement dans `process.py` peut affecter `tray.py` et `whisperx_worker.py`
- **La compatibilité des deux environnements Python** — une dépendance ajoutée dans l'env principal n'est pas disponible dans `venv-whisperx`, et vice versa
- **La cohérence avec `.env` et `.env.example`** — toute nouvelle configuration doit être exposée proprement
- **Les effets de bord CUDA** — chargement/déchargement mémoire, contexte GPU entre deux runs

### Gestion des dépendances

- **Ne jamais faire `pip install X` sans mettre à jour `requirements.txt`** — utiliser `pip freeze` ou ajouter manuellement avec la version minimale requise
- **Distinguer les deux environnements** : `requirements.txt` pour l'env principal, `venv-whisperx` a ses propres contraintes (torch~=2.8, Python 3.12)
- **Signaler les conflits de versions** dès qu'une nouvelle dépendance est envisagée, avant installation
- **Surveiller les régressions** : si une mise à jour de dépendance est faite, vérifier que CUDA, l'encodage UTF-8 et les fallbacks fonctionnent toujours
- **Préférer les versions épinglées** pour les composants critiques (torch, whisperx, ctranslate2) afin d'éviter les cassures silencieuses

### Détection proactive de problèmes

Signaler spontanément (sans attendre que l'utilisateur demande) :
- Tout pattern susceptible de causer une **fuite mémoire VRAM** (modèle chargé sans `unload`, tenseurs non libérés)
- Toute **opération bloquante** dans le thread principal du tray (risque de freeze de l'icône)
- Tout **chemin codé en dur** qui devrait être une variable d'environnement ou un paramètre
- Toute **exception silencieuse** (`except: pass` ou log sans re-raise) qui masquerait une vraie erreur
- Toute **donnée sensible** qui pourrait se retrouver dans un log, un fichier de sortie ou un commit

### Optimisations à considérer en priorité

Garder ces axes en tête lors de chaque évolution du code :

| Axe | Contexte projet |
|-----|----------------|
| **VRAM** | RTX 2080 8 Go — Whisper large-v3-turbo (1.5 Go) + WhisperX (variable) ; toujours libérer après usage |
| **Temps de traitement** | Cible : transcription < 1/5 de la durée audio sur GPU |
| **Robustesse des threads** | `tray.py` utilise des threads daemon — les exceptions non catchées tuent silencieusement le thread |
| **Encodage** | Windows CP1252 vs UTF-8 — toujours forcer `-X utf8` ou `encoding="utf-8"` explicitement |
| **Subprocess JSON** | Le canal stdout du worker est réservé au JSON — tout print de debug doit aller sur stderr |
| **Fallbacks** | Chaque composant critique (CUDA, Gemini pro, WhisperX) doit avoir un fallback documenté et testé |

### Qualité du code

- **Fonctions courtes et responsabilité unique** — `process.py` sépare déjà bien transcription / sauvegarde / génération ; maintenir cette séparation
- **Nommer explicitement les constantes** — pas de magic strings pour les noms de modèles, les chemins ou les seuils
- **Logger les états significatifs** — tout changement d'état du pipeline doit apparaître dans `tray.log` avec un préfixe clair (`[état]`, `✅`, `⚠️`, `❌`)
- **Pas de `print()` de debug laissé en production** — utiliser le système de log existant ou supprimer après diagnostic

### Sécurité applicative

- **Valider les entrées fichier** avant traitement : existence, extension, taille non nulle
- **Ne jamais interpoler `HF_TOKEN` ou `GEMINI_API_KEY`** dans des chaînes loggées ou des messages d'erreur
- **Vérifier la taille des fichiers audio** avant envoi à Gemini (limite inline : 20 Mo)
- **Nettoyer les fichiers temporaires** si un traitement échoue à mi-parcours

### Gestion des composants Python et prévention des conflits

#### Deux environnements, deux règles d'or

| Environnement | Interpréteur | Packages installés via | Ne jamais y installer |
|---|---|---|---|
| **Principal** | `D:\Utilitaires\Python\python.exe` | `pip` (env global) | torch CUDA 2.8, whisperx, ctranslate2 |
| **venv-whisperx** | `venv-whisperx\Scripts\python.exe` | `venv-whisperx\Scripts\pip` | openai-whisper, sounddevice, pystray |

Ces deux environnements doivent rester **strictement isolés**. Ne jamais installer un package de l'un dans l'autre.

#### Conflits de versions connus

| Package | Env principal | venv-whisperx | Raison du conflit |
|---|---|---|---|
| `torch` | Toute version CUDA compatible 3.14 | `2.8.0+cu128` épinglé | WhisperX exige `~=2.8.0` |
| `numpy` | Libre | `>=2.1.0` | WhisperX et pyannote exigent numpy 2.x |
| `openai-whisper` | Installé | **Absent** | Incompatible avec faster-whisper dans le même env |
| `huggingface-hub` | Libre | `<1.0.0` | Contrainte WhisperX |

#### Procédure avant d'ajouter une dépendance

1. **Identifier l'environnement cible** — le package est-il utilisé par `tray.py`/`process.py` (principal) ou par `whisperx_worker.py` (venv-whisperx) ?
2. **Vérifier la compatibilité Python** — l'env principal est Python 3.14, venv-whisperx est Python 3.12 ; certains packages ont des contraintes `requires-python`
3. **Tester l'import dans l'environnement cible** avant d'écrire du code qui en dépend :
   ```powershell
   # Env principal
   D:\Utilitaires\Python\python.exe -c "import nouveau_package"
   # venv-whisperx
   venv-whisperx\Scripts\python.exe -c "import nouveau_package"
   ```
4. **Mettre à jour `requirements.txt`** si le package va dans l'env principal
5. **Documenter dans `CLAUDE.md`** si le package est critique ou crée un conflit connu

#### Réinstallation de torch CUDA dans venv-whisperx

WhisperX réinstalle systématiquement torch en version CPU quand on le met à jour. Après tout `pip install whisperx` ou mise à jour de WhisperX dans le venv, **toujours réexécuter** :
```powershell
venv-whisperx\Scripts\pip install torch==2.8.0 torchaudio==2.8.0 `
  --index-url https://download.pytorch.org/whl/cu128 `
  --force-reinstall --no-deps
```
Puis vérifier :
```powershell
venv-whisperx\Scripts\python.exe -c "import torch; print(torch.cuda.is_available())"
# Doit afficher : True
```

#### Détection de conflits silencieux

Certains conflits ne lèvent pas d'erreur à l'import mais causent des comportements inattendus. Surveiller :
- **torch CPU au lieu de CUDA** : `torch.cuda.is_available()` retourne `False` alors que le GPU est présent → torch CPU installé par erreur
- **numpy incompatible** : erreur `AttributeError` ou `ImportError` sur des fonctions numpy → conflit de version majeure (numpy 1.x vs 2.x)
- **ctranslate2 sans CUDA** : transcription WhisperX lente et `compute_type` ignoré → vérifier que ctranslate2 détecte bien le GPU
- **openai-whisper importé depuis venv-whisperx** : les deux bibliothèques de transcription peuvent interférer si elles se retrouvent dans le même env

#### Commandes de diagnostic rapide

```powershell
# Lister les packages installés dans chaque env
D:\Utilitaires\Python\python.exe -m pip list | findstr "torch whisper"
venv-whisperx\Scripts\python.exe -m pip list | findstr "torch whisper"

# Vérifier CUDA dans les deux envs
D:\Utilitaires\Python\python.exe -c "import torch; print('Principal CUDA:', torch.cuda.is_available())"
venv-whisperx\Scripts\python.exe -c "import torch; print('WhisperX CUDA:', torch.cuda.is_available())"

# Vérifier la version numpy
D:\Utilitaires\Python\python.exe -c "import numpy; print('Principal numpy:', numpy.__version__)"
venv-whisperx\Scripts\python.exe -c "import numpy; print('WhisperX numpy:', numpy.__version__)"
```

### Veille technologique

Lors des échanges sur le projet, signaler proactivement :
- La disponibilité de nouveaux modèles Gemini stables (actuellement en preview)
- Les mises à jour majeures de WhisperX ou pyannote susceptibles de changer l'API
- Les évolutions de PyTorch CUDA qui pourraient nécessiter une réinstallation dans `venv-whisperx`
- Toute dépréciation de modèle Gemini annoncée (historique : 1.5-flash → 2.0-flash → 2.5-flash → 3.x)
