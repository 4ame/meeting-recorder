"""
process.py — Transcription Whisper locale + Compte rendu Gemini

Usage :
    python src/process.py recordings/reunion_20250615_1430.mp3
    python src/process.py --transcript output/transcription_xxx.txt  # depuis transcription existante
"""

import whisper
import numpy as np
from google import genai
import datetime
import argparse
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# --- Configuration ---
API_KEY = os.getenv("GEMINI_API_KEY")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", os.path.expanduser("~/Documents/GeneratedCR/CompteRendus"))
PROMPT_FILE = Path(__file__).parent.parent / "prompts" / "compte-rendu.md"
HF_TOKEN = os.getenv("HF_TOKEN", "")

# Chemin vers le venv WhisperX (Python 3.12)
WHISPERX_PYTHON = str(Path(__file__).parent.parent / "venv-whisperx" / "Scripts" / "python.exe")
WHISPERX_WORKER = str(Path(__file__).parent / "whisperx_worker.py")
USE_WHISPERX = os.getenv("USE_WHISPERX", "0") == "1"

# Limite API Gemini pour envoi inline (Mo)
GEMINI_INLINE_LIMIT_MB = 20

# Cache du modèle Whisper — chargé une seule fois pour éviter les erreurs CUDA
_whisper_model = None


def get_whisper_model():
    """Charge le modèle Whisper et le met en cache."""
    global _whisper_model
    if _whisper_model is None:
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"   Chargement du modèle Whisper ({WHISPER_MODEL}) sur {device.upper()}...")
        _whisper_model = whisper.load_model(WHISPER_MODEL, device=device)
        print(f"   Modèle chargé en mémoire")
    return _whisper_model


def unload_whisper_model():
    """Libère le modèle Whisper de la VRAM après transcription."""
    global _whisper_model
    if _whisper_model is not None:
        del _whisper_model
        _whisper_model = None
        import torch
        torch.cuda.empty_cache()
        print("   Modèle Whisper déchargé de la VRAM")


def load_prompt() -> str:
    """Charge le prompt système depuis prompts/compte-rendu.md."""
    if not PROMPT_FILE.exists():
        print(f"⚠️  Fichier prompt introuvable : {PROMPT_FILE}")
        print("   Utilisation d'un prompt minimal par défaut")
        return "Tu es un assistant expert en gestion de projet IT. Génère un compte rendu structuré de cette réunion."

    with open(PROMPT_FILE, "r", encoding="utf-8") as f:
        return f.read()


def load_audio_numpy(audio_path: str) -> np.ndarray:
    """Charge un fichier WAV et le convertit en float32 mono 16 kHz pour Whisper."""
    import soundfile as sf
    data, sr = sf.read(audio_path, dtype="float32")
    # Mono
    if data.ndim > 1:
        data = data.mean(axis=1)
    # Rééchantillonnage vers 16 kHz si nécessaire
    target_sr = whisper.audio.SAMPLE_RATE  # 16000
    if sr != target_sr:
        import numpy as np
        target_len = int(len(data) * target_sr / sr)
        data = np.interp(
            np.linspace(0, len(data) - 1, target_len),
            np.arange(len(data)),
            data
        ).astype("float32")
    return data


def transcribe(audio_path: str) -> str:
    """Transcrit un fichier audio localement avec Whisper ou WhisperX selon USE_WHISPERX."""
    if USE_WHISPERX:
        return transcribe_whisperx(audio_path)
    return transcribe_whisper(audio_path)


def transcribe_whisperx(audio_path: str) -> str:
    """Transcrit via WhisperX (venv Python 3.12) avec alignement et diarisation."""
    import subprocess, json

    print(f"\n🎙️  Transcription WhisperX (large-v3-turbo + diarisation)")
    print(f"   Fichier : {os.path.basename(audio_path)}")
    print("   ⏳ En cours...")

    cmd = [WHISPERX_PYTHON, "-X", "utf8", WHISPERX_WORKER, audio_path]
    if HF_TOKEN:
        cmd.append(HF_TOKEN)

    # Ajoute ffmpeg (installé via Scoop) au PATH du sous-processus
    env = os.environ.copy()
    ffmpeg_bin = r"C:\Users\arnau\scoop\apps\ffmpeg\current\bin"
    env["PATH"] = ffmpeg_bin + os.pathsep + env.get("PATH", "")

    proc = subprocess.run(cmd, capture_output=True, env=env)
    stdout = proc.stdout.decode("utf-8", errors="replace")
    stderr = proc.stderr.decode("utf-8", errors="replace")

    if proc.returncode != 0:
        raise RuntimeError(f"WhisperX worker error:\n{stderr}")

    data = json.loads(stdout)
    if "error" in data:
        raise RuntimeError(f"WhisperX: {data['error']}")

    transcription = data["transcription"]
    print(f"✅ Transcription WhisperX terminée ({len(transcription)} caractères)")
    return transcription


def transcribe_whisper(audio_path: str) -> str:
    """Transcrit un fichier audio localement avec Whisper vanilla."""
    print(f"\n🎙️  Transcription Whisper (modèle : {WHISPER_MODEL})")
    print(f"   Fichier : {os.path.basename(audio_path)}")
    print("   ⏳ En cours... (peut prendre quelques minutes)")

    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"   Device : {device.upper()}")

    try:
        model = get_whisper_model()
        audio = load_audio_numpy(audio_path)
        result = model.transcribe(audio, language="fr", verbose=False, fp16=(device == "cuda"))
    except Exception as cuda_err:
        if "CUDA" in str(cuda_err) or "cuda" in str(cuda_err):
            print(f"   ⚠️  Erreur CUDA ({cuda_err.__class__.__name__}), bascule sur CPU...")
            global _whisper_model
            _whisper_model = None  # Réinitialise le cache
            _whisper_model = whisper.load_model(WHISPER_MODEL, device="cpu")
            audio = load_audio_numpy(audio_path)
            result = _whisper_model.transcribe(audio, language="fr", verbose=False, fp16=False)
        else:
            raise

    transcription = result["text"].strip()
    print(f"✅ Transcription terminée ({len(transcription)} caractères)")

    unload_whisper_model()

    return transcription


def meeting_folder(timestamp: str) -> str:
    """Retourne le chemin du dossier dédié à la réunion (créé si nécessaire)."""
    folder = os.path.join(OUTPUT_DIR, f"reunion_{timestamp}")
    os.makedirs(folder, exist_ok=True)
    return folder


def save_transcription(transcription: str, timestamp: str) -> str:
    """Sauvegarde la transcription brute dans le dossier de la réunion."""
    folder = meeting_folder(timestamp)
    txt_path = os.path.join(folder, "transcription.txt")

    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(transcription)

    print(f"   Transcription brute : {txt_path}")
    return txt_path


def generate_report_from_audio(audio_path: str) -> str:
    """
    Envoie l'audio directement à Gemini (Option A).
    """
    if not API_KEY:
        raise ValueError("GEMINI_API_KEY manquant dans le fichier .env")

    client = genai.Client(api_key=API_KEY)
    prompt = load_prompt()

    print(f"   📁 Upload audio vers Gemini File API...")
    audio_file = client.files.upload(file=audio_path)
    response = client.models.generate_content(
        model="gemini-3.1-pro-preview",
        contents=[prompt, audio_file]
    )
    return response.text


def generate_report_from_text(transcription: str) -> str:
    """
    Envoie la transcription texte à Gemini (Options B/C/D).
    Méthode recommandée — plus rapide et sans limite de taille.
    """
    print(f"\n📤 Génération du compte rendu via Gemini...")

    if not API_KEY:
        raise ValueError("GEMINI_API_KEY manquant dans le fichier .env")

    client = genai.Client(api_key=API_KEY)
    prompt = load_prompt()
    full_prompt = f"{prompt}\n\n## Transcription de la réunion\n\n{transcription}"

    models_fallback = ["gemini-3.1-pro-preview", "gemini-3-flash-preview", "gemini-2.5-flash"]
    for model in models_fallback:
        try:
            print(f"   Modèle : {model}")
            response = client.models.generate_content(
                model=model,
                contents=full_prompt
            )
            print("✅ Compte rendu généré")
            return response.text
        except Exception as e:
            print(f"   ⚠️  {model} indisponible ({e.__class__.__name__}: {e}), tentative suivante...")

    raise RuntimeError("Tous les modèles Gemini sont indisponibles.")


def save_report(report: str, timestamp: str) -> str:
    """Sauvegarde le compte rendu dans le dossier de la réunion."""
    folder = meeting_folder(timestamp)
    md_path = os.path.join(folder, "CR.md")

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"   Compte rendu : {md_path}")
    return md_path


def run(audio_path: str):
    """Pipeline complet depuis un fichier audio."""
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")

    print(f"\n{'='*50}")
    print(f"🚀 Traitement : {os.path.basename(audio_path)}")
    print(f"{'='*50}")

    try:
        # Étape 1 : Transcription locale
        transcription = transcribe(audio_path)
        save_transcription(transcription, timestamp)

        # Étape 2 : Compte rendu via Gemini
        report = generate_report_from_text(transcription)
        md_path = save_report(report, timestamp)

        folder = meeting_folder(timestamp)
        print(f"\n🎉 Pipeline terminé avec succès !")
        print(f"   📁 Sortie : {folder}")

    except Exception as e:
        folder = meeting_folder(timestamp)
        error_path = os.path.join(folder, "erreur.txt")
        with open(error_path, "w", encoding="utf-8") as f:
            f.write(f"Fichier : {audio_path}\nErreur : {str(e)}\n")
        print(f"\n❌ Erreur : {e}")
        print(f"   Détails : {error_path}")
        sys.exit(1)


def run_from_transcript(transcript_path: str):
    """Pipeline depuis une transcription .txt existante."""
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")

    with open(transcript_path, "r", encoding="utf-8") as f:
        transcription = f.read()

    print(f"\n📄 Transcription chargée : {os.path.basename(transcript_path)}")
    report = generate_report_from_text(transcription)
    save_report(report, timestamp)
    print(f"\n🎉 Compte rendu généré depuis transcription existante")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Transcription + compte rendu réunion")
    parser.add_argument("audio", nargs="?", help="Chemin vers le fichier audio .mp3")
    parser.add_argument("--transcript", type=str, help="Chemin vers une transcription .txt existante")
    args = parser.parse_args()

    if args.transcript:
        run_from_transcript(args.transcript)
    elif args.audio:
        run(args.audio)
    else:
        print("Usage : python src/process.py <fichier.mp3>")
        print("        python src/process.py --transcript <transcription.txt>")
        sys.exit(1)
