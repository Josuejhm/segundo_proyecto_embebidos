# modules/voice_output.py
"""
Conversión de texto a voz (TTS) usando espeak-ng
VENTAJAS:
- Completamente offline, sin descargas
- Sin dependencias de modelos pesados
- Funciona en cualquier hardware
- Bajo consumo de recursos
"""

import subprocess
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class VoiceOutput:
    """Convierte texto a voz usando espeak-ng (offline)"""
    
    def __init__(self, language="es"):
        """
        Args:
            language: código idioma (es, en, etc.)
        """
        self.language = "es" if language == "es" else "en"
        self.output_dir = Path("data/audio")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Verificar que espeak-ng esté disponible
        self._check_espeak()
    
    def _check_espeak(self):
        """Verifica que espeak-ng esté instalado"""
        try:
            subprocess.run(
                ["espeak-ng", "--version"],
                capture_output=True,
                timeout=5
            )
            logger.info("✓ espeak-ng disponible")
        except FileNotFoundError:
            logger.warning("⚠️  espeak-ng no encontrado. Instala con: sudo apt-get install espeak-ng")
    
    def speak(self, text, play=True):
        """
        Convierte texto a voz y reproduce
        
        Args:
            text: texto a vocalizar
            play: si reproducir automáticamente (en espeak siempre reproduce)
            
        Returns:
            True si éxito, None si error
        """
        if not text or not text.strip():
            logger.warning("Texto vacío")
            return None
        
        try:
            # Truncar texto largo
            if len(text) > 500:
                text = text[:500] + "..."
            
            logger.info(f"Vocalizando: '{text[:50]}...'")
            
            # Ejecutar espeak-ng
            process = subprocess.run(
                ["espeak-ng", "-v", f"{self.language}", text],
                capture_output=True,
                timeout=60
            )
            
            if process.returncode == 0:
                logger.info("✓ Audio reproducido con espeak-ng")
                return True
            else:
                logger.error(f"Error en espeak-ng: {process.stderr.decode()}")
                return None
                
        except FileNotFoundError:
            logger.error("espeak-ng no encontrado. Instala con: sudo apt-get install espeak-ng")
            return None
        except subprocess.TimeoutExpired:
            logger.error("Timeout en espeak-ng")
            return None
        except Exception as e:
            logger.error(f"Error vocalizando: {e}")
            return None
    
    def speak_json(self, json_data, play=True):
        """
        Vocaliza solo la respuesta principal de JSON
        
        Args:
            json_data: dict con respuesta
            play: si reproducir
            
        Returns:
            True si éxito, None si error
        """
        if isinstance(json_data, dict):
            # Extraer solo la respuesta (no notas ni fuentes)
            text = json_data.get("respuesta", "")
            if text:
                # Limpiar texto
                text = text.replace("\n", " ")
                return self.speak(text, play=play)
        
        return None


# Función helper
def speak_text(text, play=True):
    """Helper para vocalizar texto rápidamente"""
    voice = VoiceOutput()
    return voice.speak(text, play=play)


if __name__ == "__main__":
    # Test
    voice = VoiceOutput(language="es")
    voice.speak("Hola, esto es una prueba de síntesis de voz en español con espeak.")
