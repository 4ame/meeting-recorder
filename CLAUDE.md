# Meeting Recorder — Workflow audio → compte rendu IT

## Vue d'ensemble

Pipeline Python qui enregistre l'audio d'une réunion (micro + son système),
transcrit localement via Whisper, puis génère un compte rendu structuré via
l'API Gemini. Zéro coût, zéro intervention manuelle après déclenchement.

## Stack technique

- Python 3.10+ (Windows)
- Whisper (OpenAI, local) — transcription audio
- Gemini 1.5 Flash (API Google) — génération du compte rendu
- watchdog — surveillance de dossier
- soundcard — capture audio WASAPI loopback (Option A/B)

## Structure du projet

```
meeting-recorder/
├── CLAUDE.md               ← ce fichier
├── .env                    ← clé API Gemini (ne jamais committer)
├── .env.example            ← template sans valeurs sensibles
├── .gitignore
├── requirements.txt
├── src/
│   ├── record.py           ← capture audio micro + système
│   ├── process.py          ← transcription Whisper + CR Gemini
│   └── watcher.py          ← surveillance dossier (Option C/D)
├── prompts/
│   └── compte-rendu.md     ← prompt système injecté dans Gemini
├── docs/
│   ├── options.md          ← comparatif des 4 options d'implémentation
│   ├── option-A.md
│   ├── option-B.md
│   ├── option-C.md
│   └── option-D.md         ← option recommandée
├── recordings/             ← fichiers audio (ignorés par git)
└── output/                 ← comptes rendus .md générés (ignorés par git)
```

## Commandes essentielles

```bash
# Installer les dépendances
pip install -r requirements.txt

# Tester la capture audio
python src/record.py --test

# Lancer un enregistrement (Option A/B)
python src/record.py

# Surveiller un dossier (Option C/D)
python src/watcher.py

# Traiter un fichier audio existant manuellement
python src/process.py recordings/reunion_xxx.mp3
```

## Règles importantes

- Ne jamais committer le fichier `.env` — il contient la clé API
- Les dossiers `recordings/` et `output/` sont ignorés par git
- Le prompt Gemini est dans `prompts/compte-rendu.md` — éditable sans toucher au code
- Toujours tester `record.py --test` avant une vraie réunion

## Comportement attendu de Claude Code

Quand tu travailles sur ce projet :
- Vérifie toujours que `.env` est dans `.gitignore` avant tout commit
- Teste chaque composant de manière isolée avant d'assembler le pipeline
- Si la capture audio échoue, consulte `docs/option-D.md` pour le fallback VB-Cable
- Le prompt Gemini est dans `prompts/compte-rendu.md` — importe-le avec @prompts/compte-rendu.md
