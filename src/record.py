"""
record.py — Capture audio micro + son système (Windows WASAPI loopback)

Usage :
    python src/record.py           # Enregistrement interactif (Entrée pour arrêter)
    python src/record.py --test    # Test de la capture audio (5 secondes)
    python src/record.py --output  chemin/vers/fichier.mp3
"""

import soundcard as sc
import sounddevice as sd
import soundfile as sf
import numpy as np
import threading
import queue
import datetime
import argparse
import warnings
import os
import sys
from dotenv import load_dotenv

warnings.filterwarnings("ignore", message="data discontinuity in recording")

# Force UTF-8 output on Windows to handle emoji in print statements
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

load_dotenv()

# --- Configuration ---
RECORDINGS_DIR = os.getenv("RECORDINGS_DIR", os.path.expanduser("~/Documents/GeneratedCR/Recordings"))
SAMPLE_RATE = 44100
CHANNELS = 2
CHUNK_FRAMES = int(SAMPLE_RATE * 0.5)  # 500ms par chunk
EXCLUDED_MIC_KEYWORDS = {"Steam Streaming"}

recording_chunks = []
stop_event = threading.Event()


def list_audio_devices():
    """Affiche les périphériques audio disponibles pour diagnostic."""
    print("\n🎧 Périphériques de lecture (son système) :")
    for speaker in sc.all_speakers():
        print(f"  - {speaker.name}")

    print("\n🎤 Périphériques d'enregistrement (micros) :")
    for d in sd.query_devices():
        if d['max_input_channels'] > 0:
            print(f"  - {d['name']}")


def get_loopback_device():
    """Récupère le périphérique loopback (son système) via soundcard."""
    try:
        default_speaker = sc.default_speaker()
        loopback = sc.get_microphone(id=str(default_speaker.name), include_loopback=True)
        return loopback
    except Exception as e:
        print(f"⚠️  Impossible d'accéder au loopback : {e}")
        print("   → Vérifier que le Stereo Mix est activé dans les paramètres son Windows")
        print("   → Alternative : installer VB-Cable (https://vb-audio.com/Cable/)")
        return None


def get_mic_device():
    """Retourne l'index sounddevice du micro par défaut Windows (Steam exclus)."""
    # Micro par défaut sounddevice = micro par défaut Windows
    default_info = sd.query_devices(kind='input')
    default_name = default_info['name']

    if not any(kw in default_name for kw in EXCLUDED_MIC_KEYWORDS):
        try:
            # Test rapide
            test = sd.rec(int(SAMPLE_RATE * 0.05), samplerate=SAMPLE_RATE,
                          channels=1, dtype='float32', blocking=True)
            return None, SAMPLE_RATE  # None = utilise le défaut sounddevice
        except Exception:
            pass

    # Fallback : parcourir les devices disponibles
    for i, d in enumerate(sd.query_devices()):
        if d['max_input_channels'] == 0:
            continue
        if any(kw in d['name'] for kw in EXCLUDED_MIC_KEYWORDS):
            continue
        try:
            test = sd.rec(int(d['default_samplerate'] * 0.05),
                          samplerate=int(d['default_samplerate']),
                          channels=1, device=i, dtype='float32', blocking=True)
            return i, int(d['default_samplerate'])
        except Exception:
            continue

    return None, None


def to_stereo(data: np.ndarray) -> np.ndarray:
    """Convertit un tableau audio en stéréo (shape N×2)."""
    if data.ndim == 1:
        return np.stack([data, data], axis=1)
    if data.shape[1] == 1:
        return np.concatenate([data, data], axis=1)
    return data


def resample_to(data: np.ndarray, from_sr: int, to_sr: int) -> np.ndarray:
    """Rééchantillonnage linéaire simple si les sample rates diffèrent."""
    if from_sr == to_sr:
        return data
    target_len = int(len(data) * to_sr / from_sr)
    result = np.zeros((target_len, data.shape[1]), dtype=data.dtype)
    for ch in range(data.shape[1]):
        result[:, ch] = np.interp(
            np.linspace(0, len(data) - 1, target_len),
            np.arange(len(data)),
            data[:, ch]
        )
    return result


def record_audio():
    """Capture micro (sounddevice) + loopback (soundcard) et mixe les deux flux."""
    loopback = get_loopback_device()
    mic_idx, mic_sr = get_mic_device()

    if mic_sr is None:
        print("❌ Aucun micro fonctionnel trouvé")
        return

    mic_info = sd.query_devices(mic_idx, kind='input') if mic_idx is not None else sd.query_devices(kind='input')
    print(f"🎤 Micro : {mic_info['name']} ({mic_sr} Hz)")

    mic_queue = queue.Queue()

    def mic_callback(indata, frames, time_info, status):
        mic_queue.put(indata.copy())

    mic_chunk = int(mic_sr * 0.5)

    with sd.InputStream(device=mic_idx, channels=1, samplerate=mic_sr,
                        dtype='float32', blocksize=mic_chunk, callback=mic_callback):

        if loopback:
            print(f"🔊 Son système : {loopback.name}")
            try:
                with loopback.recorder(samplerate=SAMPLE_RATE, channels=CHANNELS) as lb_rec:
                    while not stop_event.is_set():
                        lb_data = to_stereo(lb_rec.record(numframes=CHUNK_FRAMES))
                        try:
                            mic_raw = mic_queue.get(timeout=1.0)
                        except queue.Empty:
                            mic_raw = np.zeros((mic_chunk, 1), dtype='float32')
                        mic_data = resample_to(to_stereo(mic_raw), mic_sr, SAMPLE_RATE)
                        # Aligne les longueurs avant le mix
                        n = min(len(lb_data), len(mic_data))
                        recording_chunks.append((lb_data[:n] + mic_data[:n]) / 2)
                return
            except Exception as e:
                print(f"⚠️  Erreur loopback : {e} — bascule sur micro uniquement")

        # Fallback : micro uniquement
        print("⚠️  Enregistrement micro uniquement (son système indisponible)")
        while not stop_event.is_set():
            try:
                mic_raw = mic_queue.get(timeout=1.0)
                recording_chunks.append(to_stereo(mic_raw))
            except queue.Empty:
                continue


def save_recording(output_path: str = None) -> str:
    """Assemble les chunks et sauvegarde le fichier audio."""
    os.makedirs(RECORDINGS_DIR, exist_ok=True)

    if output_path is None:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        output_path = os.path.join(RECORDINGS_DIR, f"reunion_{timestamp}.wav")

    audio_data = np.concatenate(recording_chunks, axis=0)
    sf.write(output_path, audio_data, SAMPLE_RATE)

    duration = len(audio_data) / SAMPLE_RATE
    print(f"✅ Audio sauvegardé : {output_path}")
    print(f"   Durée : {duration / 60:.1f} min | Taille : {os.path.getsize(output_path) / 1024 / 1024:.1f} MB")

    return output_path


def test_capture(duration: int = 5):
    """Test rapide de la capture audio (5 secondes)."""
    print(f"\n🧪 Test de capture audio ({duration} secondes)...")
    list_audio_devices()

    stop_event.clear()
    t = threading.Thread(target=record_audio)
    t.start()

    import time
    time.sleep(duration)
    stop_event.set()
    t.join()

    if recording_chunks:
        test_path = os.path.join(RECORDINGS_DIR, "test_capture.wav")
        save_recording(test_path)
        print("✅ Test réussi — vérifie le fichier audio généré")
    else:
        print("❌ Aucun audio capturé — vérifier les périphériques")


def start(output_path: str = None):
    """Démarre l'enregistrement interactif."""
    print("\n⏺  Enregistrement démarré")
    print("   Appuyez sur Entrée pour arrêter...\n")

    stop_event.clear()
    t = threading.Thread(target=record_audio)
    t.start()

    input()  # Attendre l'action de l'utilisateur
    stop_event.set()
    t.join()

    print("\n⏹  Enregistrement arrêté")
    audio_path = save_recording(output_path)

    # Lancer automatiquement le traitement
    import process
    process.run(audio_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Enregistrement audio réunion")
    parser.add_argument("--test", action="store_true", help="Test de capture (5 secondes)")
    parser.add_argument("--output", type=str, help="Chemin de sortie du fichier audio")
    parser.add_argument("--devices", action="store_true", help="Lister les périphériques audio")
    args = parser.parse_args()

    if args.devices:
        list_audio_devices()
    elif args.test:
        test_capture()
    else:
        start(args.output)
