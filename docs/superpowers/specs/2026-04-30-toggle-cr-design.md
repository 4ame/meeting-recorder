# Toggle génération CR — Design

**Date :** 2026-04-30  
**Statut :** approuvé  

## Contexte

L'utilisation d'une clé API Gemini personnelle n'est plus envisageable. La transcription doit rester fonctionnelle. L'utilisateur veut pouvoir activer ou désactiver la génération du compte rendu depuis l'interface tray, sans toucher au code ni aux fichiers de configuration.

## Objectif

Ajouter un toggle "Générer le CR" dans le menu clic-droit du tray. L'état est persisté entre les sessions. Valeur par défaut : désactivé.

## Architecture

### Nouveau fichier : `src/config.py`

Responsabilité unique : lire et écrire `~/.meeting_recorder/settings.json`.

```python
# Interface publique
load_settings() -> dict    # retourne {"cr_enabled": False} par défaut
save_settings(data: dict)  # écrit atomiquement via json.dump
```

- Le dossier `~/.meeting_recorder/` est créé si absent.
- Si le fichier est absent ou corrompu, retourne les valeurs par défaut sans planter.
- Aucune dépendance externe.

### Fichier de config utilisateur

`~/.meeting_recorder/settings.json` :
```json
{"cr_enabled": false}
```

Emplacement choisi pour séparer clairement préférences utilisateur et code projet, sans risque de commit accidentel.

### Modifications `tray.py`

**Variable globale ajoutée :**
```python
_cr_enabled: bool  # initialisée au démarrage depuis config.load_settings()
```

**Item menu ajouté** (entre les séparateurs, toujours visible) :
```
Démarrer l'enregistrement
Annuler le traitement        (visible si _processing)
Ouvrir la progression        (visible si _processing)
──────────────────────────
✓ Générer le CR              (checkmark natif pystray si activé)
──────────────────────────
Ouvrir le dossier des CR
──────────────────────────
Quitter
```

Au clic : bascule `_cr_enabled`, sauvegarde via `config.save_settings()`.

**Flux `process_async` conditionnel :**

```
transcribe() → save_transcription()
  ↓
if _cr_enabled:
    generate_report_from_text() → save_report()
    notification "Compte rendu prêt ✓"
    os.startfile(OUTPUT_DIR)
else:
    notification "Transcription prête ✓"
    os.startfile(dossier_reunion)   # dossier contenant transcription.txt
```

### Pas de modification à `process.py`

Toute la logique de branchement reste dans `tray.py`. `process.py` n'est pas au courant du toggle.

## Gestion des erreurs

- Fichier config absent ou JSON invalide → valeurs par défaut silencieusement (`cr_enabled: false`)
- Erreur d'écriture → loggée dans `tray.log`, le toggle reste opérationnel en mémoire pour la session

## Ce qui n'est PAS dans ce scope

- Modification de `process.py`
- Option CLI `--no-cr` pour les appels manuels
- Variable d'environnement `GENERATE_CR`
- Tests automatisés du toggle (la fonction est triviale, le comportement est testé manuellement)
