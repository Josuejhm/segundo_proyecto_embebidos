"""
modules/input_handler.py
------------------------
Maneja entrada de texto y salida de voz del sistema.

VERSIÓN SIMPLIFICADA (Jetson 2 GB):

  ELIMINADO — STT (Speech-to-Text / Whisper.cpp):
    - No se dispone de micrófono en el hardware actual.
    - Whisper.cpp consume ~100 MB RAM adicional que no hay en 2 GB.
    - La entrada es siempre por teclado o pantalla táctil.

  CONSERVADO — TTS (Text-to-Speech / Piper):
    - Piper TTS vocaliza las respuestas al agricultor.
    - Se invoca como proceso CLI (subprocess.run), NO como daemon.
    - Pico de RAM: ~80 MB durante ~10 segundos → luego el proceso muere.
    - Detección defensiva del parlante USB: si no hay dispositivo USB
      de audio disponible, el TTS falla silenciosamente sin crashear.

COMPATIBILIDAD DE PARLANTES USB:
    Cualquier parlante USB estándar de PC que use UAC 1.0 (USB Audio Class)
    funciona sin drivers adicionales en Linux. Los más comunes usan el chip
    CM108/CM109. El módulo del kernel `snd-usb-audio` los detecta
    automáticamente cuando se enchufan.

    Para verificar que el parlante está detectado:
        aplay -l        → debe mostrar "USB Audio Device" o similar
        aplay -D hw:1,0 /usr/share/sounds/alsa/Front_Left.wav  → prueba directa

    Si ALSA usa HDMI en lugar del USB como salida por defecto, instalar:
        /etc/asound.conf con: defaults.pcm.card 1 / defaults.ctl.card 1
    (Esta configuración va en la receta Yocto meta-agri-edge/recipes-multimedia/alsa-config/)
"""

import logging
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)


def vocalizar_respuesta(
    texto:      str,
    model_path: str,
    bin_path:   str = "piper",
    config_path: Optional[str] = None,
) -> bool:
    """
    Vocaliza el texto usando Piper TTS a través del parlante USB.

    Flujo:
      1. Verificar que hay un dispositivo de audio USB disponible.
      2. Piper convierte texto → audio RAW PCM (22050 Hz, S16_LE, mono).
      3. aplay reproduce el audio en el parlante USB.

    Args:
        texto:       Texto a vocalizar (máximo 200 chars recomendado).
        model_path:  Ruta al archivo .onnx del modelo de voz en español.
        bin_path:    Ruta al ejecutable de Piper.
        config_path: Ruta al .onnx.json (opcional, Piper lo infiere si no se pasa).

    Returns:
        True si la vocalización fue exitosa, False en cualquier fallo.
        Los fallos son silenciosos (no crashean la aplicación).
    """
    if not texto or not texto.strip():
        logger.debug("TTS: texto vacío, omitiendo.")
        return False

    if not model_path:
        logger.warning("TTS: model_path no configurado en settings.yaml.")
        return False

    # ── Paso 1: verificar parlante USB ────────────────────────────────────────
    if not _verificar_audio_usb():
        logger.warning(
            "TTS omitido: no se detectó parlante USB.\n"
            "  Verificar: aplay -l\n"
            "  Si el parlante aparece como card 0 (no card 1), "
            "revisar /etc/asound.conf."
        )
        return False

    # ── Paso 2: construir comando Piper ───────────────────────────────────────
    cmd_piper = [bin_path, "--model", model_path, "--output-raw"]
    if config_path:
        cmd_piper += ["--config", config_path]

    # ── Paso 3: pipeline Piper | aplay ────────────────────────────────────────
    # Piper genera PCM raw → aplay lo reproduce.
    # Se usa subprocess.run (bloqueante) para que el proceso Piper termine
    # ANTES de que Python continúe, liberando así los ~80 MB de RAM.
    try:
        texto_bytes = texto.encode("utf-8")

        piper_proc = subprocess.run(
            cmd_piper,
            input          = texto_bytes,
            capture_output = True,
            timeout        = 30,    # máximo 30s para generar audio
        )

        if piper_proc.returncode != 0:
            logger.warning(
                "Piper falló (código %d): %s",
                piper_proc.returncode,
                piper_proc.stderr.decode(errors="replace")[:200],
            )
            return False

        # Reproducir el audio generado por Piper
        aplay_proc = subprocess.run(
            [
                "aplay",
                "-r", "22050",   # Sample rate de Piper
                "-f", "S16_LE",  # Formato PCM 16-bit little-endian
                "-c", "1",       # Mono
                "-",             # Leer desde stdin
            ],
            input   = piper_proc.stdout,
            timeout = 60,   # máximo 60s para reproducir
            capture_output = True,
        )

        if aplay_proc.returncode != 0:
            logger.warning(
                "aplay falló (código %d): %s",
                aplay_proc.returncode,
                aplay_proc.stderr.decode(errors="replace")[:200],
            )
            return False

        logger.info("TTS: '%s...' vocalizado exitosamente.", texto[:40])
        return True

    except subprocess.TimeoutExpired:
        logger.warning("TTS: timeout — texto muy largo o Piper muy lento.")
        return False

    except FileNotFoundError as e:
        # Piper no está instalado o no está en PATH
        logger.warning(
            "TTS: ejecutable no encontrado: %s\n"
            "  En Jetson verificar que la receta piper-tts esté en la imagen Yocto.\n"
            "  En desarrollo: instalar Piper desde https://github.com/rhasspy/piper",
            e,
        )
        return False

    except Exception as e:
        logger.warning("TTS: error inesperado (no crítico): %s", e)
        return False


def _verificar_audio_usb() -> bool:
    """
    Verifica que hay al menos un dispositivo de audio USB disponible.

    Revisa la salida de `aplay -l` buscando "USB" en los nombres de tarjeta.
    Si no hay dispositivo USB, el audio saldría por HDMI o no saldría.

    Retorna True también si aplay no está disponible (para no bloquear
    pruebas en PC de desarrollo sin parlante USB).
    """
    try:
        proc = subprocess.run(
            ["aplay", "-l"],
            capture_output = True,
            text    = True,
            timeout = 3,
        )
        salida = proc.stdout.lower()
        # Buscar indicadores de dispositivo USB de audio
        if any(k in salida for k in ("usb", "usb audio", "usb device", "cm108", "cm109")):
            return True
        # Si no hay tarjetas listadas en absoluto, probablemente no hay ALSA
        if "no soundcards found" in salida:
            logger.warning("TTS: ALSA no encuentra ninguna tarjeta de audio.")
            return False
        # Hay tarjetas pero ninguna es USB → probablemente solo HDMI
        logger.info(
            "TTS: no se detectó parlante USB. Dispositivos disponibles:\n%s",
            proc.stdout[:300],
        )
        return False

    except FileNotFoundError:
        # aplay no está instalado → entorno de desarrollo sin audio
        logger.debug("TTS: aplay no disponible (entorno sin audio). Omitiendo verificación.")
        return True   # Retornar True para no bloquear pruebas en PC

    except Exception as e:
        logger.debug("TTS: no se pudo verificar audio USB: %s", e)
        return True   # Permisivo en desarrollo