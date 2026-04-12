# Comparatif des options d'implémentation

## Tableau synthétique

| Option | Capture audio | Transcription | CR | Complexité | Coût |
|---|---|---|---|---|---|
| A | Python WASAPI | Gemini direct | Gemini | Moyenne | Gratuit |
| B | Python WASAPI | Whisper local | Gemini | Moyenne | Gratuit |
| C | OBS Studio | Whisper local | Gemini | Élevée | Gratuit |
| **D** ⭐ | Enregistreur Windows | Whisper local | Gemini | Faible | Gratuit |

## Arbre de décision

```
Stereo Mix disponible sur ton PC ?
    │
    ├── OUI → Option B
    │
    └── NON → Tu veux installer OBS ?
                    │
                    ├── OUI → Option C
                    └── NON → Option D ⭐
```

## Détails par option

- `option-A.md` — Python + Gemini direct
- `option-B.md` — Python + Whisper + Gemini
- `option-C.md` — OBS + Whisper + Gemini
- `option-D.md` — Enregistreur Windows + Whisper + Gemini (recommandée)
