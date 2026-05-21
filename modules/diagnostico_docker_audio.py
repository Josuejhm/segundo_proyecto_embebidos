#!/usr/bin/env python3
"""
DIAGNÓSTICO DE AUDIO DENTRO DE DOCKER
Script para verificar si el audio funciona en el contenedor
"""

import subprocess
import sys

def run_cmd(cmd, description):
    """Ejecuta comando y muestra resultado"""
    print(f"\n{'='*60}")
    print(f"🔍 {description}")
    print(f"{'='*60}")
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(f"⚠️  {result.stderr[:200]}")
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print("⏱️  Timeout")
        return False
    except Exception as e:
        print(f"❌ {e}")
        return False

def test_python_audio():
    """Test módulos Python de audio"""
    print(f"\n{'='*60}")
    print("🔍 MÓDULOS PYTHON DE AUDIO")
    print(f"{'='*60}")
    
    modules = [
        ("sounddevice", "import sounddevice as sd; print(f'✓ sounddevice {sd.__version__}')"),
        ("numpy", "import numpy as np; print(f'✓ numpy {np.__version__}')"),
        ("whisper", "import whisper; print('✓ whisper disponible')"),
    ]
    
    for name, code in modules:
        try:
            subprocess.run(
                ["python3", "-c", code],
                capture_output=True,
                text=True,
                timeout=5
            )
            print(f"✅ {name}")
        except:
            print(f"❌ {name}")

def main():
    print("\n" + "🎤 "*30)
    print("  DIAGNÓSTICO DE AUDIO EN DOCKER")
    print("🎤 "*30)
    
    print("\n📍 Ubicación: Dentro del contenedor Docker")
    print("📍 Si ves esto, el contenedor está corriendo correctamente\n")
    
    # 1. ALSA
    run_cmd("aplay -l", "1️⃣  DISPOSITIVOS ALSA (grabación/reproducción)")
    run_cmd("arecord -l", "1️⃣  DISPOSITIVOS ALSA (grabación)")
    
    # 2. PulseAudio
    success = run_cmd("pactl info", "2️⃣  INFORMACIÓN DE PULSEAUDIO")
    if not success:
        print("⚠️  PulseAudio no disponible (posiblemente esperado en Docker)")
    
    run_cmd("pactl list short sources", "2️⃣  FUENTES PULSEAUDIO (micrófonos)")
    run_cmd("pactl list short sinks", "2️⃣  SALIDAS PULSEAUDIO (altavoces)")
    
    # 3. Módulos Python
    test_python_audio()
    
    # 4. Grabación test
    print(f"\n{'='*60}")
    print("🔍 4️⃣  PRUEBA DE GRABACIÓN")
    print(f"{'='*60}")
    
    try:
        code = """
import sounddevice as sd
import numpy as np

print('🎤 Grabando 2 segundos a 16kHz...')
audio = sd.rec(int(2*16000), samplerate=16000, channels=1, dtype='float32')
sd.wait()

rms = np.sqrt(np.mean(audio**2))
peak = np.max(np.abs(audio))

print(f'✓ Audio capturado:')
print(f'  Duración: {len(audio)/16000:.2f}s')
print(f'  RMS Level: {rms:.6f}')
print(f'  Peak Level: {peak:.6f}')

if rms < 0.001:
    print(f'  ⚠️  MUY SILENCIOSO - Aumenta volumen del micrófono')
elif rms > 0.5:
    print(f'  ⚠️  MUY FUERTE - Puede estar distorsionado')
else:
    print(f'  ✅ Nivel OK')
"""
        subprocess.run(["python3", "-c", code], timeout=10)
    except Exception as e:
        print(f"❌ Error: {e}")
    
    # 5. Whisper test
    print(f"\n{'='*60}")
    print("🔍 5️⃣  PRUEBA DE WHISPER")
    print(f"{'='*60}")
    
    try:
        code = """
import whisper
import numpy as np

print('📥 Cargando modelo tiny...')
model = whisper.load_model('tiny')

print('🧪 Creando audio de prueba (ruido blanco)...')
audio = np.random.randn(16000*3).astype('float32') * 0.1

print('🔄 Transcribiendo...')
result = model.transcribe(audio, language='es', verbose=False, fp16=False)

print('✓ Transcripción completada (aunque sea ruido)')
print(f'  Resultado: {result.get(\"text\", \"[vacío]\")[:50]}')
"""
        subprocess.run(["python3", "-c", code], timeout=30)
    except Exception as e:
        print(f"❌ Error: {e}")
    
    # 6. Variables de entorno
    print(f"\n{'='*60}")
    print("🔍 6️⃣  VARIABLES DE ENTORNO")
    print(f"{'='*60}")
    
    env_vars = [
        "ALSA_CARD",
        "ALSA_DEVICE", 
        "PULSE_SERVER",
        "PULSEAUDIO_PROP_MEDIA_NAME",
        "LD_LIBRARY_PATH"
    ]
    
    for var in env_vars:
        value = subprocess.run(
            f"echo ${var}",
            shell=True,
            capture_output=True,
            text=True
        ).stdout.strip()
        status = "✅" if value else "⚠️"
        print(f"{status} {var}: {value or '(no establecida)'}")
    
    # 7. Directorios
    print(f"\n{'='*60}")
    print("🔍 7️⃣  DIRECTORIOS")
    print(f"{'='*60}")
    
    dirs = [
        "/dev/snd",
        "/run/user/1000/pulse",
        "/app/data/audio",
        "/app/data/logs"
    ]
    
    for dir_path in dirs:
        try:
            result = subprocess.run(
                f"ls -ld {dir_path}",
                shell=True,
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.returncode == 0:
                print(f"✅ {dir_path}")
            else:
                print(f"⚠️  {dir_path} (no encontrado)")
        except:
            print(f"❌ {dir_path} (error)")
    
    # Resumen
    print(f"\n{'='*60}")
    print("📋 PRÓXIMOS PASOS")
    print(f"{'='*60}\n")
    
    print("""
Si TODO está ✅:
  → Audio funciona en Docker
  → Ejecuta: python3 main.py

Si hay ⚠️ en ALSA/PulseAudio:
  → Normal en Docker, sounddevice usará PortAudio

Si hay ❌ en grabación:
  → Host: verificar micrófono conectado
  → Host: sudo systemctl restart pulseaudio
  → Host: alsamixer (subir volumen)

Si hay ❌ en Whisper:
  → Reconstruir: docker-compose build --no-cache
  → O usar voice_input_FIXED.py con normalización

Información completa: DOCKER_AUDIO_GUIA.md
    """)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n❌ Diagnóstico cancelado")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)
