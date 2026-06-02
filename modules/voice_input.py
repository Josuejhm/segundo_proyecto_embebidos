# modules/voice_input.py — VERSIÓN JETSON (whisper.cpp via subprocess)
"""
STT usando whisper.cpp (binario C++, compatible con CUDA 10.2 y ARM64).
Interfaz idéntica al archivo anterior para no romper input_handler.py.

INSTALACIÓN en Jetson:
  git clone https://github.com/ggerganov/whisper.cpp
  cd whisper.cpp && make -j4
  bash models/download-ggml-model.sh tiny
  sudo cp main /usr/local/bin/whisper-cpp

EN DESARROLLO (PC): el mismo binario compilado para x86.
"""
import logging
import os
import subprocess
import tempfile
import wave
import numpy as np
import sounddevice as sd

logger = logging.getLogger(__name__)

WHISPER_BIN   = os.environ.get("WHISPER_BIN",   "/usr/local/bin/whisper-cpp")
WHISPER_MODEL = os.environ.get("WHISPER_MODEL",  "data/models/ggml-tiny.bin")
SAMPLE_RATE   = 16000


class VoiceInput:
    """STT usando whisper.cpp via subprocess. Interfaz compatible con versión anterior."""

    def __init__(self, model_size: str = "tiny", language: str = "es"):
        self.model_size = model_size
        self.language   = language
        self.sample_rate = SAMPLE_RATE
        self.available  = self._check_disponible()

    def _check_disponible(self) -> bool:
        bin_ok   = os.path.exists(WHISPER_BIN)
        model_ok = os.path.exists(WHISPER_MODEL)
        if not bin_ok:
            logger.warning("whisper.cpp no encontrado en %s", WHISPER_BIN)
        if not model_ok:
            logger.warning("Modelo no encontrado en %s", WHISPER_MODEL)
        return bin_ok and model_ok

    def listen_and_transcribe(self, duration: int = 15, record_sr: int = 16000) -> str | None:
        """Graba audio y transcribe. Misma interfaz que la versión anterior."""
        if not self.available:
            print("STT no disponible. Verificar whisper.cpp y modelo.")
            return None

        try:
            print(f"\nPresioná ENTER para iniciar grabación ({duration}s máx.)")
            input()
            print("Grabando... presioná ENTER para detener")

            audio = sd.rec(int(duration * SAMPLE_RATE), samplerate=SAMPLE_RATE,
                           channels=1, dtype="int16", blocking=False)
            input()
            sd.stop(); sd.wait()

            if audio is None or np.all(audio == 0):
                print("No se capturó audio.")
                return None

            # Guardar WAV temporal
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                wav_path = f.name

            with wave.open(wav_path, "w") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)   # int16 = 2 bytes
                wf.setframerate(SAMPLE_RATE)
                wf.writeframes(audio.tobytes())

            # Llamar a whisper.cpp
            result = subprocess.run(
                [WHISPER_BIN, "-m", WHISPER_MODEL, "-f", wav_path,
                 "-l", self.language, "--no-timestamps", "-otxt"],
                capture_output=True, text=True, timeout=60
            )
            os.unlink(wav_path)

            texto = result.stdout.strip()
            if texto:
                print(f"Transcripción: {texto}")
                return texto
            else:
                print("No se reconoció texto.")
                return None

        except KeyboardInterrupt:
            sd.stop()
            return None
        except subprocess.TimeoutExpired:
            logger.error("whisper.cpp tardó más de 60s")
            return None
        except Exception as e:
            logger.error("Error en STT: %s", e)
            return None