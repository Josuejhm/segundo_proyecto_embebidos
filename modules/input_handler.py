# modules/input_handler.py
"""
Manejador unificado de entrada (texto o voz)
Permite elegir entre escribir o grabar en cualquier modalidad
"""

import logging
from typing import Optional
from modules.voice_input import VoiceInput
from modules.voice_output import VoiceOutput

logger = logging.getLogger(__name__)


def solicitar_entrada(prompt: str, modo: str = "texto_o_voz") -> Optional[str]:
    """
    Solicita entrada al usuario (texto o voz)
    
    Args:
        prompt: mensaje a mostrar
        modo: "texto_o_voz" (pregunta), "solo_texto", "solo_voz"
    
    Returns:
        str texto capturado o None
    """
    
    if modo == "solo_texto":
        return input(prompt).strip()
    
    if modo == "solo_voz":
        return _capturar_voz(prompt)
    
    # Modo "texto_o_voz": pregunta al usuario
    print(prompt)
    opcion = input("¿Escribir o grabar? [e/G]: ").strip().lower()
    
    if opcion == "e":
        # Escribir
        return input("Escriba: ").strip()
    else:
        # Grabar (por defecto)
        return _capturar_voz()


def _capturar_voz(prompt: str = "") -> Optional[str]:
    """
    Captura voz del micrófono
    
    Args:
        prompt: mensaje opcional antes de grabar
    
    Returns:
        str transcripción o None si error
    """
    try:
        if prompt:
            print(f"\n{prompt}")
        
        print("🎤 Inicializando captura de voz...")
        voice_in = VoiceInput(model_size="base", language="es")
        
        print("🎤 Presiona Enter para comenzar a grabar")
        print("   (máximo 15 segundos, presiona Ctrl+C para detener)")
        input()
        
        texto = voice_in.listen_and_transcribe(duration=15)
        
        if texto:
            print(f"✅ Capturado: '{texto}'")
            return texto
        else:
            print("❌ No se capturó audio")
            return None
            
    except ImportError:
        print("❌ Whisper no disponible. Instala: pip install openai-whisper")
        return None
    except KeyboardInterrupt:
        print("\n✓ Grabación cancelada")
        return None
    except Exception as e:
        logger.error(f"Error en captura de voz: {e}")
        print(f"❌ Error: {e}")
        return None


def vocalizar_respuesta(json_data: dict) -> bool:
    """
    Vocaliza la respuesta JSON si es posible
    
    Args:
        json_data: dict con campo "respuesta"
    
    Returns:
        bool True si se vocalizó, False si error
    """
    try:
        if not isinstance(json_data, dict):
            return False
        
        respuesta_texto = json_data.get("respuesta", "")
        if not respuesta_texto:
            return False
        
        print("\n🔊 Vocalizando respuesta...")
        voice_out = VoiceOutput(language="es")
        voice_out.speak(respuesta_texto, play=True)
        print("✓ Respuesta vocalizada")
        return True
        
    except ImportError:
        print("❌ Piper TTS no disponible. Instala: pip install piper-tts")
        return False
    except Exception as e:
        logger.warning(f"Error vocalizando: {e}")
        return False


if __name__ == "__main__":
    # Test
    texto = solicitar_entrada("Escribe o graba tu pregunta:", "texto_o_voz")
    if texto:
        print(f"Resultado: {texto}")
