"""
whisperx_worker.py — Transcription WhisperX avec diarisation

Appelé par process.py via subprocess dans le venv dédié (Python 3.12).
Usage :
    venv-whisperx/Scripts/python.exe src/whisperx_worker.py <audio_path> [hf_token]

Sortie JSON sur stdout :
    {
        "segments": [{"start": 0.0, "end": 2.5, "text": "...", "speaker": "SPEAKER_00"}, ...],
        "transcription": "texte complet"
    }
"""

import sys
import json
import os

# Force UTF-8 sur stdout et stderr pour éviter la corruption des accents sur Windows (CP1252)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Ajoute FFmpeg (Scoop) au PATH avant tout import pour torchcodec et whisperx.load_audio
_ffmpeg_bin = r"C:\Users\arnau\scoop\apps\ffmpeg\current\bin"
if os.path.exists(_ffmpeg_bin):
    os.environ["PATH"] = _ffmpeg_bin + os.pathsep + os.environ.get("PATH", "")

def _emit(step: str, pct: float, message: str) -> None:
    """Émet un événement de progression sur stderr en JSON. Ne lève jamais d'exception."""
    try:
        line = json.dumps({"type": "progress", "step": step, "pct": pct, "message": message}, ensure_ascii=False)
        print(line, file=sys.stderr, flush=True)
    except Exception:
        pass

def main():
    # Redirige stdout vers stderr pour que les logs n'interfèrent pas avec le JSON
    _real_stdout = sys.stdout
    sys.stdout = sys.stderr

    if len(sys.argv) < 2:
        sys.stdout = _real_stdout
        print(json.dumps({"error": "Usage: whisperx_worker.py <audio_path> [hf_token]"}))
        sys.exit(1)

    audio_path = sys.argv[1]
    hf_token = sys.argv[2] if len(sys.argv) > 2 else os.getenv("HF_TOKEN")

    try:
        import torch
        import whisperx

        device = "cuda" if torch.cuda.is_available() else "cpu"
        compute_type = "float16" if device == "cuda" else "int8"

        # Étape 1 — Transcription
        _emit("transcription", 0.0, "Chargement modèle large-v3-turbo...")
        model = whisperx.load_model("large-v3-turbo", device=device, compute_type=compute_type, language="fr")
        _emit("transcription", 0.3, "Transcription en cours...")
        audio = whisperx.load_audio(audio_path)
        result = model.transcribe(audio, batch_size=16, language="fr")
        _emit("transcription", 0.7, "Transcription terminée")

        # Libère la VRAM avant l'alignement
        del model
        torch.cuda.empty_cache()

        # Étape 2 — Alignement temporel mot à mot
        _emit("alignment", 0.0, "Chargement modèle d'alignement...")
        model_a, metadata = whisperx.load_align_model(language_code="fr", device=device)
        result = whisperx.align(result["segments"], model_a, metadata, audio, device, return_char_alignments=False)
        _emit("alignment", 1.0, "Alignement terminé")

        del model_a
        torch.cuda.empty_cache()

        # Étape 3 — Diarisation (optionnelle si token HuggingFace disponible)
        if hf_token:
            _emit("diarization", 0.0, "Diarisation en cours...")
            diarize_model = whisperx.diarize.DiarizationPipeline(
                model_name="pyannote/speaker-diarization-3.1",
                token=hf_token,
                device=device
            )
            diarize_segments = diarize_model(audio)
            result = whisperx.assign_word_speakers(diarize_segments, result)
            _emit("diarization", 1.0, "Diarisation terminée")

        # Construction de la transcription complète avec speakers
        segments = result.get("segments", [])
        lines = []
        current_speaker = None
        for seg in segments:
            speaker = seg.get("speaker", "")
            text = seg.get("text", "").strip()
            if not text:
                continue
            if speaker and speaker != current_speaker:
                current_speaker = speaker
                lines.append(f"\n[{speaker}]")
            lines.append(text)

        transcription = " ".join(lines).strip()

        output = {
            "segments": [
                {
                    "start": seg.get("start"),
                    "end": seg.get("end"),
                    "text": seg.get("text", "").strip(),
                    "speaker": seg.get("speaker", "")
                }
                for seg in segments
            ],
            "transcription": transcription
        }

        # Restaure stdout et écrit le JSON en UTF-8 pur dans le buffer binaire
        sys.stdout = _real_stdout
        output_json = json.dumps(output, ensure_ascii=False)
        sys.stdout.buffer.write(output_json.encode("utf-8") + b"\n")
        sys.stdout.buffer.flush()

    except Exception as exc:
        sys.stdout = _real_stdout
        error_json = json.dumps({"error": str(exc)}, ensure_ascii=False)
        _real_stdout.buffer.write(error_json.encode("utf-8") + b"\n")
        _real_stdout.buffer.flush()
        sys.exit(1)


if __name__ == "__main__":
    main()
