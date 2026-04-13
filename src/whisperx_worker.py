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

    import torch
    import whisperx

    device = "cuda" if torch.cuda.is_available() else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"

    # Étape 1 — Transcription
    model = whisperx.load_model("large-v3-turbo", device=device, compute_type=compute_type, language="fr")
    audio = whisperx.load_audio(audio_path)
    result = model.transcribe(audio, batch_size=16, language="fr")

    # Libère la VRAM avant l'alignement
    del model
    torch.cuda.empty_cache()

    # Étape 2 — Alignement temporel mot à mot
    model_a, metadata = whisperx.load_align_model(language_code="fr", device=device)
    result = whisperx.align(result["segments"], model_a, metadata, audio, device, return_char_alignments=False)

    del model_a
    torch.cuda.empty_cache()

    # Étape 3 — Diarisation (optionnelle si token HuggingFace disponible)
    if hf_token:
        diarize_model = whisperx.DiarizationPipeline(use_auth_token=hf_token, device=device)
        diarize_segments = diarize_model(audio)
        result = whisperx.assign_word_speakers(diarize_segments, result)

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

    # Restaure stdout et écrit uniquement le JSON
    sys.stdout = _real_stdout
    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
