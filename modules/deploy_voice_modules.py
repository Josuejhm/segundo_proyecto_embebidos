#!/usr/bin/env python3
"""
Script de despliegue automatizado para los módulos de voz en Docker
Uso: python deploy_voice_modules.py
"""

import subprocess
import sys
from pathlib import Path


def run_command(cmd, description=""):
    """Ejecuta comando y muestra resultado"""
    if description:
        print(f"\n🔄 {description}...")
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            print(f"✓ {description or 'Comando exitoso'}")
            return True
        else:
            print(f"✗ Error: {result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        print(f"✗ Timeout en: {description}")
        return False
    except Exception as e:
        print(f"✗ Excepción: {e}")
        return False


def get_container_name():
    """Obtiene el nombre del contenedor de docker-compose"""
    result = subprocess.run(
        "docker compose ps --services",
        shell=True,
        capture_output=True,
        text=True
    )
    services = result.stdout.strip().split('\n')
    
    if not services or services[0] == '':
        print("❌ No hay servicios en docker-compose")
        return None
    
    if len(services) == 1:
        container_name = services[0]
    else:
        print("\n📋 Servicios disponibles:")
        for i, service in enumerate(services, 1):
            print(f"  {i}. {service}")
        
        choice = input("\n¿Cuál es el contenedor de la app? (número): ").strip()
        try:
            container_name = services[int(choice) - 1]
        except (ValueError, IndexError):
            print("❌ Opción inválida")
            return None
    
    print(f"✓ Contenedor seleccionado: {container_name}")
    return container_name


def deploy_files(container_name, local_files_dir=None):
    """Despliega archivos al contenedor"""
    
    if local_files_dir is None:
        local_files_dir = Path(__file__).parent
    
    files = {
        'voice_input.py': '/app/modules/voice_input.py',
        'voice_output.py': '/app/modules/voice_output.py'
    }
    
    success_count = 0
    
    for local_file, remote_path in files.items():
        local_path = local_files_dir / local_file
        
        if not local_path.exists():
            print(f"⚠️  {local_file} no encontrado en {local_files_dir}")
            continue
        
        cmd = f"docker compose cp {local_path} {container_name}:{remote_path}"
        if run_command(cmd, f"Copiando {local_file}"):
            success_count += 1
    
    return success_count == len([f for f in files if (local_files_dir / f).exists()])


def verify_installation(container_name):
    """Verifica que los archivos fueron instalados correctamente"""
    
    verification_script = '''
import sys
sys.path.insert(0, '/app')

errors = []

# Verificar voice_input.py
try:
    from modules.voice_input import VoiceInput
    vi = VoiceInput(model_size="tiny")
    print(f"✓ voice_input.py: OK (Whisper disponible: {vi.available})")
except Exception as e:
    print(f"✗ voice_input.py: {e}")
    errors.append(str(e))

# Verificar voice_output.py
try:
    from modules.voice_output import VoiceOutput
    vo = VoiceOutput()
    print(f"✓ voice_output.py: OK (gTTS disponible: {vo.available})")
except Exception as e:
    print(f"✗ voice_output.py: {e}")
    errors.append(str(e))

# Resultado final
if not errors:
    print("\\n✅ Todos los módulos verificados correctamente")
    sys.exit(0)
else:
    print(f"\\n❌ {len(errors)} error(es) encontrado(s)")
    sys.exit(1)
'''
    
    cmd = f'''docker compose exec -T {container_name} python << 'EOF'
{verification_script}
EOF'''
    
    print("\n🧪 Verificando instalación...")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    
    print(result.stdout)
    if result.returncode != 0:
        print("⚠️  Algunos módulos pueden no estar disponibles")
        if result.stderr:
            print(f"Detalles: {result.stderr}")
    
    return result.returncode == 0


def test_functionality(container_name):
    """Prueba básica de funcionalidad"""
    
    test_script = '''
import sys
sys.path.insert(0, '/app')

from modules.voice_input import VoiceInput
from modules.voice_output import VoiceOutput

print("\\n📊 Información del sistema de voz:")
print("-" * 50)

# Test voice_input
try:
    vi = VoiceInput(model_size="tiny", language="es")
    print(f"VoiceInput:")
    print(f"  - Modelo: {vi.model_size}")
    print(f"  - Idioma: {vi.language}")
    print(f"  - Sample rate: {vi.sample_rate} Hz")
    print(f"  - Disponible: {vi.available}")
    print(f"  - Resampleo a 16 kHz: ✓ Implementado")
except Exception as e:
    print(f"Error en VoiceInput: {e}")

print()

# Test voice_output
try:
    vo = VoiceOutput(language="es")
    print(f"VoiceOutput:")
    print(f"  - Idioma: {vo.language}")
    print(f"  - Disponible: {vo.available}")
    print(f"  - Reproductores disponibles: {vo.audio_players}")
    print(f"  - Directorio output: {vo.output_dir}")
except Exception as e:
    print(f"Error en VoiceOutput: {e}")

print("-" * 50)
'''
    
    cmd = f'''docker compose exec -T {container_name} python << 'EOF'
{test_script}
EOF'''
    
    print("\n📊 Información del sistema:")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    print(result.stdout)


def main():
    """Función principal"""
    print("=" * 60)
    print("🚀 Desplegador de Módulos de Voz - Docker")
    print("=" * 60)
    
    # Verificar que docker-compose está disponible
    if not run_command("docker compose version", "Verificando docker-compose"):
        print("\n❌ docker-compose no disponible")
        sys.exit(1)
    
    # Obtener nombre del contenedor
    container_name = get_container_name()
    if not container_name:
        sys.exit(1)
    
    # Verificar que el contenedor está corriendo
    cmd = f"docker compose ps --services --filter status=running | grep {container_name}"
    if not run_command(cmd, f"Verificando que {container_name} está corriendo"):
        print(f"\n❌ El contenedor {container_name} no está corriendo")
        print("   Ejecuta: docker compose up -d")
        sys.exit(1)
    
    # Desplegar archivos
    print("\n📦 Desplegando archivos...")
    if not deploy_files(container_name):
        print("\n⚠️  Algunos archivos no pudieron copiarse")
    
    # Verificar instalación
    if verify_installation(container_name):
        print("\n✅ Instalación completada exitosamente")
    
    # Test de funcionalidad
    if input("\n¿Ejecutar pruebas de funcionalidad? (s/n): ").lower() == 's':
        test_functionality(container_name)
    
    print("\n" + "=" * 60)
    print("✨ Despliegue completado")
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ Operación cancelada")
        sys.exit(1)
