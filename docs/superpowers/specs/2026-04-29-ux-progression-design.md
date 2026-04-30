# Design — UX progression & contrôle du traitement

**Date :** 2026-04-29  
**Statut :** approuvé  
**Fichiers impactés :** `src/whisperx_worker.py`, `src/process.py`, `src/tray.py`, `src/progress_window.py` (nouveau)

---

## Contexte

Le pipeline actuel (enregistrement → transcription → CR Gemini) est opaque une fois lancé : l'icône tray change de couleur mais n'indique ni la progression réelle, ni l'étape précise. En cas d'erreur, l'utilisateur doit ouvrir `tray.log`. Il n'existe aucun moyen d'annuler un traitement en cours.

## Objectifs

1. **Progression visible** — afficher l'étape et le pourcentage sans ouvrir tray.log
2. **Annulation propre** — interrompre le traitement en conservant ce qui est déjà produit
3. **Feedback de fin enrichi** — notification toast avec durée réunion, temps de traitement, modèle utilisé
4. **Erreurs lisibles** — message court dans la toast, pas besoin de fouiller tray.log pour le cas commun

## Architecture

### Vue d'ensemble

```
whisperx_worker.py  ──stderr JSON──►  process.py  ──callbacks──►  tray.py
                                                              └──►  ProgressWindow (tkinter)
```

Un **bus d'événements léger** : `process.py` publie des `ProgressEvent`, `tray.py` et `ProgressWindow` s'y abonnent via un callback `on_progress` passé au démarrage du pipeline.

### ProgressEvent

Dataclass immuable définie dans `process.py` :

```python
@dataclass
class ProgressEvent:
    step: str        # "transcription" | "alignment" | "diarization" | "gemini" | "done" | "error"
    pct: float       # 0.0 – 1.0 (-1.0 = indéterminé)
    message: str     # description courte affichée dans l'UI
```

## Protocole de progression — stderr JSON

`whisperx_worker.py` émet des événements sur stderr (canal déjà réservé aux logs). Stdout reste exclusivement réservé au JSON résultat final — compatibilité ascendante garantie.

**Format :**
```json
{"type": "progress", "step": "transcription", "pct": 0.0, "message": "Chargement modèle large-v3-turbo..."}
```

**Étapes émises par le worker :**

| `step` | `pct` | Moment |
|---|---|---|
| `transcription` | 0.0 | Avant `load_model` |
| `transcription` | 0.3 | Après `load_model`, avant `transcribe` |
| `transcription` | 0.7 | Après `transcribe`, avant `align` |
| `alignment` | 0.0 | Avant `load_align_model` |
| `alignment` | 1.0 | Après `align` |
| `diarization` | 0.0 | Avant `DiarizationPipeline` (si HF_TOKEN présent) |
| `diarization` | 1.0 | Après `assign_word_speakers` |

Pour **Whisper vanilla**, `process.py` émet directement les événements (pas de subprocess à lire) :
- `pct=0.0` au chargement modèle
- `pct=0.5` au lancement de `transcribe`
- `pct=1.0` à la fin

Les lignes non-JSON sur stderr sont ignorées silencieusement — les logs texte existants restent inchangés.

## Refactoring `process.py`

### Passage à Popen

```python
# Avant
proc = subprocess.run(cmd, capture_output=True, env=env)

# Après
proc = subprocess.Popen(cmd, stdout=PIPE, stderr=PIPE, env=env)
_current_proc = proc  # référence globale pour l'annulation
```

### Thread de lecture stderr

Un thread daemon est lancé dès le démarrage du subprocess. Il lit stderr ligne par ligne, tente un `json.loads`, et appelle `on_progress(ProgressEvent(...))` si le parsing réussit. Il se termine naturellement à la fin du subprocess.

### Signature mise à jour

```python
def transcribe_whisperx(audio_path: str, on_progress=None) -> str
def transcribe_whisper(audio_path: str, on_progress=None) -> str
def transcribe(audio_path: str, on_progress=None) -> str
```

`on_progress` est optionnel — les appels CLI (`python src/process.py fichier.wav`) fonctionnent sans changement.

### Annulation

`process.py` expose :
```python
def cancel() -> None
```

Comportement :
1. Appelle `_current_proc.terminate()` si un subprocess WhisperX est actif
2. Lève un flag `_cancel_requested` consulté dans la boucle Gemini

**Règle "garder ce qui est prêt" :** `tray.py` appelle `save_transcription` avant `generate_report_from_text`. Si l'annulation survient pendant Gemini, `transcription.txt` est déjà sur disque. Si elle survient pendant WhisperX, aucun fichier n'a encore été écrit.

## Changements `tray.py`

### Tooltip dynamique

`_set_state` reçoit un paramètre `detail` optionnel :
```
Meeting Recorder — Transcription WhisperX · alignement 100%
Meeting Recorder — Génération CR · gemini-2.5-pro [perso]
```

### Menu contextuel par état

| État | Entrées |
|---|---|
| Idle | Démarrer l'enregistrement |
| Recording | Arrêter et générer le CR |
| Processing | Annuler le traitement · Ouvrir progression · *(Démarrer désactivé)* |

### Notifications toast enrichies

- **Succès :** durée réunion + temps total traitement + modèle Gemini utilisé
- **Annulation :** `Traitement annulé — transcription.txt conservée` ou `Traitement annulé`
- **Erreur :** message court directement dans la toast + action secondaire `Ouvrir tray.log`

### tray.log

Passage du mode `"w"` à `"a"` (append) avec horodatage de session, pour conserver l'historique entre les redémarrages.

## Nouveau fichier `src/progress_window.py`

Fenêtre tkinter non-redimensionnable, toujours au premier plan (`topmost=True`), style `toolwindow`.

### Layout

```
┌─────────────────────────────────────────┐
│  Meeting Recorder                        │
│                                          │
│  Étape    Transcription WhisperX         │
│  ████████████░░░░░░░░░  70%              │
│                                          │
│  Alignement temporel...                  │
│                                          │
│  ⏱ 1 min 24 s écoulées                  │
│                                          │
│              [ Annuler ]                 │
└─────────────────────────────────────────┘
```

### Comportement

- `ttk.Progressbar` en mode **indéterminé** pour les étapes sans `pct` fiable (génération Gemini)
- Chronomètre mis à jour toutes les secondes via `after(1000, ...)`
- Bouton "Annuler" : appelle `process.cancel()` puis ferme la fenêtre
- Succès : affiche `✅ Terminé` 2 secondes puis se ferme automatiquement
- Erreur : affiche le message court + bouton `Ouvrir tray.log`
- Fermeture manuelle : le traitement continue en arrière-plan, le tray prend le relais

### Thread-safety

Tous les appels tkinter depuis `on_progress` passent par `window.after(0, lambda: ...)`. La fenêtre tourne dans son propre thread : `threading.Thread(target=window.mainloop, daemon=True)`.

### Intégration dans `tray.py`

```python
# Dans process_async()
win = ProgressWindow(on_cancel=process.cancel)
threading.Thread(target=win.mainloop, daemon=True).start()
transcription = process.transcribe(audio_path, on_progress=win.update)
```

## Fichiers non touchés

- `src/record.py` — capture audio inchangée
- `prompts/compte-rendu.md` — prompt Gemini inchangé
- `src/watcher.py` — non utilisé en production
- `.env` / `.env.example` — aucune nouvelle variable

## Résumé des changements

| Fichier | Type | Description |
|---|---|---|
| `src/whisperx_worker.py` | Modification mineure | +4 lignes d'émission d'événements JSON sur stderr |
| `src/process.py` | Refactoring ciblé | `run` → `Popen`, thread stderr, callbacks, `cancel()` |
| `src/tray.py` | Extension | Tooltip dynamique, menu état, toasts enrichies, log append |
| `src/progress_window.py` | Nouveau | Fenêtre tkinter de progression |
