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
import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from subprocess import PIPE
from dotenv import load_dotenv
from dataclasses import dataclass

load_dotenv()


@dataclass(frozen=True)
class ProgressEvent:
    step: str     # "transcription"|"alignment"|"diarization"|"gemini"|"done"|"error"
    pct: float    # 0.0–1.0 ; -1.0 = indéterminé (progressbar en mode bounce)
    message: str  # description courte affichée dans l'UI


class ProcessCancelled(Exception):
    pass

_cancel_requested: bool = False
_current_proc = None  # subprocess.Popen actif, None sinon
_last_model_used: str = ""  # rempli par generate_report_from_text


def cancel() -> None:
    """Interrompt le traitement en cours : termine le subprocess WhisperX et lève le flag."""
    global _cancel_requested, _current_proc
    _cancel_requested = True
    if _current_proc is not None:
        try:
            _current_proc.terminate()
        except OSError:
            pass
        _current_proc = None


def _reset_cancel() -> None:
    """Remet le flag à zéro avant chaque nouveau traitement."""
    global _cancel_requested
    _cancel_requested = False


def _emit(on_progress, step: str, pct: float, message: str) -> None:
    """Appelle le callback on_progress si présent."""
    if on_progress is not None:
        on_progress(ProgressEvent(step=step, pct=pct, message=message))

# --- Configuration ---
API_KEY = os.getenv("GEMINI_API_KEY")
API_KEY_COMPANY = os.getenv("GEMINI_API_KEY_COMPANY")
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


def transcribe(audio_path: str, on_progress=None) -> str:
    """Transcrit un fichier audio localement avec Whisper ou WhisperX selon USE_WHISPERX."""
    if USE_WHISPERX:
        return transcribe_whisperx(audio_path, on_progress=on_progress)
    return transcribe_whisper(audio_path, on_progress=on_progress)


def transcribe_whisperx(audio_path: str, on_progress=None) -> str:
    """Transcrit via WhisperX (venv Python 3.12) avec alignement et diarisation."""
    global _current_proc

    print(f"\n🎙️  Transcription WhisperX (large-v3-turbo + diarisation)")
    print(f"   Fichier : {os.path.basename(audio_path)}")
    print("   ⏳ En cours...")

    _emit(on_progress, "transcription", 0.0, "Lancement WhisperX...")

    cmd = [WHISPERX_PYTHON, "-X", "utf8", WHISPERX_WORKER, audio_path]

    env = os.environ.copy()
    ffmpeg_bin = r"C:\Users\arnau\scoop\apps\ffmpeg\current\bin"
    env["PATH"] = ffmpeg_bin + os.pathsep + env.get("PATH", "")
    if HF_TOKEN:
        env["HF_TOKEN"] = HF_TOKEN  # transmis via env, pas en arg CLI (sécurité)

    proc = subprocess.Popen(cmd, stdout=PIPE, stderr=PIPE, env=env)
    _current_proc = proc
    stderr_lines: list[str] = []

    def _read_stderr() -> None:
        for raw in proc.stderr:
            line = raw.decode("utf-8", errors="replace").rstrip()
            stderr_lines.append(line)
            if on_progress:
                try:
                    data = json.loads(line)
                    if data.get("type") == "progress":
                        on_progress(ProgressEvent(
                            step=data["step"],
                            pct=data["pct"],
                            message=data.get("message", ""),
                        ))
                except (json.JSONDecodeError, KeyError):
                    pass

    t = threading.Thread(target=_read_stderr, daemon=True)
    t.start()

    try:
        stdout_data = proc.stdout.read()
        proc.wait()
        t.join(timeout=5.0)
    finally:
        _current_proc = None

    if proc.returncode != 0:
        raise RuntimeError("WhisperX worker error:\n" + "\n".join(stderr_lines))

    try:
        data = json.loads(stdout_data.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"WhisperX: réponse stdout invalide ({exc})\nStderr:\n" + "\n".join(stderr_lines)
        ) from exc

    if "error" in data:
        raise RuntimeError(f"WhisperX: {data['error']}")

    transcription = data["transcription"]
    print(f"✅ Transcription WhisperX terminée ({len(transcription)} caractères)")
    return transcription


def transcribe_whisper(audio_path: str, on_progress=None) -> str:
    """Transcrit un fichier audio localement avec Whisper vanilla."""
    print(f"\n🎙️  Transcription Whisper (modèle : {WHISPER_MODEL})")
    print(f"   Fichier : {os.path.basename(audio_path)}")
    print("   ⏳ En cours... (peut prendre quelques minutes)")

    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"   Device : {device.upper()}")
    _emit(on_progress, "transcription", 0.0, f"Chargement modèle {WHISPER_MODEL}...")

    try:
        model = get_whisper_model()
        _emit(on_progress, "transcription", 0.3, "Transcription en cours...")
        audio = load_audio_numpy(audio_path)
        result = model.transcribe(audio, language="fr", verbose=False, fp16=(device == "cuda"))
        _emit(on_progress, "transcription", 1.0, "Transcription terminée")
    except Exception as cuda_err:
        if "CUDA" in str(cuda_err) or "cuda" in str(cuda_err):
            print(f"   ⚠️  Erreur CUDA ({cuda_err.__class__.__name__}), bascule sur CPU...")
            global _whisper_model
            _whisper_model = None  # Réinitialise le cache
            _whisper_model = whisper.load_model(WHISPER_MODEL, device="cpu")
            audio = load_audio_numpy(audio_path)
            _emit(on_progress, "transcription", 0.5, "Bascule CPU, transcription en cours...")
            result = _whisper_model.transcribe(audio, language="fr", verbose=False, fp16=False)
            _emit(on_progress, "transcription", 1.0, "Transcription terminée (CPU)")
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


def generate_report_from_text(transcription: str, on_progress=None) -> str:
    """
    Envoie la transcription texte à Gemini (Options B/C/D).
    Méthode recommandée — plus rapide et sans limite de taille.
    """
    global _last_model_used
    print(f"\n📤 Génération du compte rendu via Gemini...")

    if not API_KEY:
        raise ValueError("GEMINI_API_KEY manquant dans le fichier .env")

    client = genai.Client(api_key=API_KEY)
    prompt = load_prompt()
    full_prompt = f"{prompt}\n\n## Transcription de la réunion\n\n{transcription}"

    debug = os.getenv("GEMINI_DEBUG", "0") == "1"

    # Priorité aux modèles pro (perso puis entreprise), puis fallback flash
    attempts = []
    if API_KEY:
        attempts.append((API_KEY, "gemini-2.5-pro"))
    if API_KEY_COMPANY:
        attempts.append((API_KEY_COMPANY, "gemini-3.1-pro-preview"))
    if API_KEY:
        attempts += [
            (API_KEY, "gemini-3-flash-preview"),
            (API_KEY, "gemini-2.5-flash"),
        ]
    if API_KEY_COMPANY:
        attempts += [
            (API_KEY_COMPANY, "gemini-3-flash-preview"),
            (API_KEY_COMPANY, "gemini-2.5-flash"),
        ]

    for api_key, model in attempts:
        if _cancel_requested:
            raise ProcessCancelled("Traitement annulé par l'utilisateur")
        key_label = "perso" if api_key == API_KEY else "entreprise"
        try:
            _emit(on_progress, "gemini", -1.0, f"{model} [{key_label}]...")
            print(f"   Modèle : {model} [{key_label}]")
            if debug:
                print(f"   [DEBUG] Prompt : {len(full_prompt)} caractères")
                print(f"   [DEBUG] Envoi requête...")
            c = genai.Client(api_key=api_key)
            response = c.models.generate_content(
                model=model,
                contents=full_prompt
            )
            if debug:
                print(f"   [DEBUG] Réponse reçue : {len(response.text)} caractères")
                print(f"   [DEBUG] Usage tokens : {getattr(response, 'usage_metadata', 'N/A')}")
            _last_model_used = f"{model} [{key_label}]"
            print("✅ Compte rendu généré")
            return response.text
        except Exception as e:
            print(f"   ⚠️  {model} [{key_label}] indisponible ({e.__class__.__name__}: {e}), tentative suivante...")
            if debug:
                import traceback
                print(f"   [DEBUG] Traceback complet :\n{traceback.format_exc()}")

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
