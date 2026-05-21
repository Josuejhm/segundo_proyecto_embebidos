# modules/voice_input.py (CORREGIDO)
"""
Captura de audio del micrófono y conversión a texto (STT) usando Whisper
SOLUCIONES:
- Resampling robusto sin scipy
- Normalización de audio para evitar NaN
- Mejor manejo de errores
"""

import logging
import warnings
from pathlib import Path
import numpy as np

# Suprimir warnings de deprecación de Whisper
warnings.filterwarnings("ignore")

logger = logging.getLogger(__name__)

try:
    import sounddevice as sd
    import whisper
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False
    logger.warning("Whisper o sounddevice no disponibles. Funcionalidad de voz deshabilitada.")


class VoiceInput:
    """Captura audio y convierte a texto usando Whisper"""
    
    def __init__(self, model_size="base", language="es"):
        """
        Args:
            model_size: "tiny", "base", "small", "medium", "large"
            language: código idioma ISO-639-1 (es, en, fr, etc.)
        """
        self.model_size = model_size
        self.language = language
        self.model = None
        self.sample_rate = 16000  # ✅ CAMBIO: Usar 16kHz directamente (estándar de Whisper)
        self.available = WHISPER_AVAILABLE
        
        if WHISPER_AVAILABLE:
            self._load_model()
    
    def _load_model(self):
        """Carga modelo Whisper (primera vez tarda)"""
        try:
            logger.info(f"Cargando modelo Whisper {self.model_size}...")
            self.model = whisper.load_model(self.model_size)
            logger.info("✓ Modelo Whisper cargado")
            self.available = True
        except Exception as e:
            logger.error(f"Error cargando Whisper: {e}")
            self.model = None
            self.available = False
    
    @staticmethod
    def _normalize_audio(audio):
        """
        Normaliza audio para evitar NaN y valores inválidos
        
        Args:
            audio: numpy array de audio
            
        Returns:
            audio normalizado entre -1 y 1
        """
        if audio is None or len(audio) == 0:
            return None
        
        # Convertir a float32
        audio = np.asarray(audio, dtype=np.float32)
        
        # Remover NaN/Inf si existen
        audio = np.nan_to_num(audio, nan=0.0, posinf=0.0, neginf=0.0)
        
        # Calcular RMS (root mean square)
        rms = np.sqrt(np.mean(audio**2))
        
        # Evitar división por cero
        if rms < 1e-10:
            logger.warning("Audio muy silencioso o vacío")
            return audio
        
        # Normalizar a [-1, 1]
        audio = audio / (rms * 20)  # Escala de amplitud
        
        # Clamp a rango válido
        audio = np.clip(audio, -1.0, 1.0)
        
        return audio
    
    @staticmethod
    def _resample_audio(audio, orig_sr, target_sr=16000):
        """
        Resampling robusto sin scipy (evita NaN)
        
        Args:
            audio: numpy array
            orig_sr: sample rate original
            target_sr: sample rate destino (default 16000)
            
        Returns:
            audio resampled
        """
        if orig_sr == target_sr:
            return audio
        
        if audio is None or len(audio) == 0:
            return audio
        
        audio = np.asarray(audio, dtype=np.float32).flatten()
        
        # Calcular índices para resampleo lineal
        num_samples = int(len(audio) * target_sr / orig_sr)
        indices = np.linspace(0, len(audio) - 1, num_samples)
        
        # Interpolación lineal simple
        audio_resampled = np.interp(indices, np.arange(len(audio)), audio)
        
        # Validar que no haya NaN
        if np.any(np.isnan(audio_resampled)):
            logger.warning("Resampling produjo NaN, usando audio original")
            return audio
        
        return audio_resampled.astype(np.float32)
    
    def record_audio(self, duration=5, prompt="Escuchando... (presiona Ctrl+C para detener)"):
        """
        Graba audio del micrófono
        
        Args:
            duration: segundos a grabar (máx)
            prompt: mensaje a mostrar
            
        Returns:
            numpy array de audio o None si error
        """
        if not WHISPER_AVAILABLE:
            logger.error("Whisper no disponible")
            return None
        
        try:
            print(f"\n🎤 {prompt}")
            print(f"   (Duración máxima: {duration}s, presiona Ctrl+C para terminar)")
            
            # Grabar audio a 16kHz directamente
            audio = sd.rec(
                int(duration * self.sample_rate),
                samplerate=self.sample_rate,
                channels=1,
                dtype='float32'
            )
            sd.wait()  # Esperar a que termine
            
            print("✓ Audio capturado")
            return audio
            
        except KeyboardInterrupt:
            print("\n✓ Grabación detenida")
            return None
        except Exception as e:
            logger.error(f"Error grabando audio: {e}")
            return None
    
    def transcribe(self, audio):
        """
        Convierte audio a texto usando Whisper
        
        Args:
            audio: numpy array de audio
            
        Returns:
            str texto transcrito o None si error
        """
        if not self.available or self.model is None:
            logger.error("Modelo Whisper no cargado")
            return None
        
        if audio is None:
            return None
        
        try:
            logger.info("Transcribiendo audio...")
            
            # Normalizar audio
            audio = self._normalize_audio(audio)
            
            result = self.model.transcribe(
                audio,
                language=self.language,
                verbose=False,
                fp16=False  # ✅ Usar float32, no float16
            )
            
            text = result.get("text", "").strip()
            
            if text:
                logger.info(f"Transcripción: {text}")
                return text
            else:
                logger.warning("No se detectó audio")
                return None
                
        except Exception as e:
            logger.error(f"Error en transcripción: {e}")
            return None
    
    def listen_and_transcribe(self, duration=15, record_sr=48000):
        """
        Captura audio con control por Enter.
        - Presiona ENTER para iniciar grabación
        - Presiona ENTER de nuevo para detener
        
        Args:
            duration: duración máxima en segundos
            record_sr: sample rate para grabación (48000 para ALSA/USB)
            
        Returns:
            str texto transcrito o None si error/vacío
        """
        if not self.available:
            print("❌ Voz no disponible (sounddevice no instalado)")
            return None
        
        if self.model is None:
            print("❌ Modelo Whisper no cargado")
            return None
        
        try:
            print("\n🎤 Presiona ENTER para iniciar grabación")
            input()  # Esperar a que presione enter
            
            print(f"🎤 Grabando ({duration}s máximo)...")
            print("   Presiona ENTER de nuevo para detener")
            
            # Grabar audio a 48kHz si es posible (ALSA/USB más estable)
            audio = sd.rec(
                int(duration * record_sr),
                samplerate=record_sr,
                channels=1,
                dtype=np.float32,
                blocking=False
            )
            
            # Esperar a que presione enter para detener
            input()
            sd.stop()
            sd.wait()  # Asegurar que se grabó todo
            
            # Validar que hay audio
            if audio is None or len(audio) == 0:
                print("❌ No se capturó audio")
                return None
            
            audio = audio.flatten()
            
            if np.all(audio == 0):
                print("❌ Audio vacío o silencio total")
                return None
            
            # Detectar nivel de ruido
            rms = np.sqrt(np.mean(audio**2))
            if rms < 0.01:
                print("⚠️  Audio muy silencioso, intenta hablar más fuerte")
                return None
            
            print(f"✓ Audio capturado (nivel: {rms:.4f})")
            print("🔄 Transcribiendo con Whisper...")
            
            # ✅ CAMBIO: Resamplear de 48kHz a 16kHz de forma robusta
            if record_sr != 16000:
                audio = self._resample_audio(audio, record_sr, 16000)
                print(f"  Resampling: {record_sr} Hz → 16000 Hz")
            
            # ✅ CAMBIO: Normalizar antes de pasar a Whisper
            audio = self._normalize_audio(audio)
            
            if audio is None:
                print("❌ Error procesando audio")
                return None
            
            # Transcribir
            result = self.model.transcribe(
                audio,
                language=self.language,
                verbose=False,
                fp16=False  # Usar float32
            )
            
            text = result.get("text", "").strip()
            if text:
                print(f"✓ Texto: {text}")
                return text
            else:
                print("❌ No se reconoció texto en el audio")
                return None
                
        except KeyboardInterrupt:
            print("\n❌ Grabación cancelada")
            sd.stop()
            return None
        except Exception as e:
            print(f"❌ Error grabando: {e}")
            logger.error(f"Error en listen_and_transcribe: {e}", exc_info=True)
            sd.stop()
            return None


# Función helper para uso rápido
def get_voice_input(duration=10):
    """Helper para obtener entrada de voz rápidamente"""
    if not WHISPER_AVAILABLE:
        print("❌ Whisper no disponible. Instala: pip install openai-whisper")
        return None
    
    voice = VoiceInput(model_size="base", language="es")
    return voice.listen_and_transcribe(duration=duration)


if __name__ == "__main__":
    # Test
    voice = VoiceInput()
    text = voice.listen_and_transcribe()
    if text:
        print(f"\nTranscripción: {text}")
