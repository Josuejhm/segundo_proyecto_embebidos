# 🚀 Instrucciones Rápidas: Docker + Yocto-Qwen

**Tiempo total estimado**: 20 minutos de setup + 6-12 horas de compilación

---

## 📋 PASO 1: Preparar el Repositorio (5 minutos)

```bash
# Opción A: Si ya tienes el repo original
cd /ruta/a/yocto-jetson-ollama

# Opción B: Si no, clonar primero
git clone https://github.com/johan-carvajal-godinez/yocto-jetson-ollama
cd yocto-jetson-ollama
```

**Copiar archivos Docker** (descargas en la carpeta anterior):

```bash
# Copiar los 6 archivos Docker al repo
cp Dockerfile docker-compose.yml docker-entrypoint.sh .
cp .dockerignore .env.example Makefile .

# Verificar estructura
ls -la | grep -E "Dockerfile|docker-compose|docker-entrypoint|Makefile"
# Output debe mostrar 4 archivos
```

---

## 🔧 PASO 2: Construir Imagen Docker (10-15 minutos)

```bash
# Construir imagen Docker (primera vez)
docker-compose build --no-cache

# O si prefieres usar make
make build
```

**¿Qué está pasando?**
- Descargando Ubuntu 22.04 base
- Instalando herramientas Yocto (gcc, bitbake, git, etc.)
- Creando usuario "builder"
- Tagging como `yocto-qwen:latest`

---

## 🚀 PASO 3: Iniciar Contenedor (2 minutos)

```bash
# Iniciar contenedor en background
docker-compose up -d

# O si prefieres make
make up

# Verificar que está corriendo
docker-compose ps
# Status debe decir "Up"
```

---

## ⚙️ PASO 4: Setup Inicial de Yocto (15-20 minutos - SOLO PRIMERA VEZ)

```bash
# Ejecutar setup automático
docker-compose exec builder /entrypoint.sh init

# O si prefieres make
make init
```

**¿Qué está pasando?**
- ✅ Descargando capas Yocto (poky, meta-tegra, meta-openembedded, etc.)
- ✅ Configurando meta-qwen
- ✅ Inicializando BitBake
- ✅ Creando local.conf y bblayers.conf

⏳ Espera a que diga "✅ Inicialización completada"

---

## 🔨 PASO 5: Compilar Imagen Yocto (6-12 horas)

```bash
# Compilar imagen con script automático
docker-compose exec builder /yocto/scripts/build-image-qwen.sh

# O si prefieres make
make build-image
```

**¿Qué está pasando?**
```
🔨 Compilando imagen Yocto con Qwen...
⏳ Iniciando BitBake (esto puede tomar 6-12 horas)...
[10 %] pkg_name ...
[20 %] pkg_name ...
...
✅ Build completado!
📦 Archivos en: /yocto/build/tmp/deploy/images/jetson-nano-devkit/
```

**Mientras compila**, abre otra terminal para monitorear:

```bash
# Ver logs en tiempo real
docker-compose logs -f builder

# Ver uso de CPU/RAM
docker stats yocto-qwen-builder

# Ver espacio en disco
docker-compose exec builder df -h /yocto
```

---

## ✅ PASO 6: Verificar Build Exitoso

Una vez que veas el mensaje "✅ Build completado!", verifica:

```bash
# Entrar al contenedor
docker-compose exec builder bash

# Ver imagen generada (dentro del contenedor)
ls -lh /yocto/build/tmp/deploy/images/jetson-nano-devkit/

# Debería mostrar algo como:
# jetson-nano-qwen-image-jetson-nano-devkit.tar.gz        (3.2G)
# jetson-nano-qwen-image-jetson-nano-devkit.tegraflash.tar.gz
# other files...

# Salir del contenedor
exit
```

---

## 💾 PASO 7: Extraer Imagen al Host

```bash
# Crear directorio output si no existe
mkdir -p output

# Copiar imagen del contenedor al host
docker-compose cp \
  builder:/yocto/build/tmp/deploy/images/jetson-nano-devkit/ \
  ./output/

# Verificar en el host
ls -lh output/jetson-nano-devkit/*.tar.gz
```

---

## 📝 COMANDOS ÚTILES (Referencia Rápida)

```bash
# ===== Ver estado =====
docker-compose ps              # Estado del contenedor
make status                    # Estado con recursos
make space                     # Uso de disco
docker-compose logs -f         # Ver logs

# ===== Entrar al contenedor =====
docker-compose exec builder bash     # Shell usuario
docker-compose exec -u root builder bash  # Shell root

# ===== Recompilar (rápido) =====
make build-image-fast

# ===== Limpiar =====
docker-compose stop            # Parar sin eliminar
docker-compose down            # Parar y eliminar
make clean-build              # Limpiar build anterior

# ===== Hacer Mostrar =====
make help                      # Todos los comandos disponibles
make info                      # Info del setup
make print-config            # Config actual
```

---

## 🎯 Flujo Completo en Comandos

**Si tienes make instalado:**

```bash
# Opción 1: Paso a paso
make build      # 10-15 min
make up         # <1 min
make init       # 15-20 min
make build-image # 6-12 horas

# Opción 2: Automático
make full-setup  # Build + up + init
make build-image # Build

# Opción 3: Todo junto (no recomendado)
make full-setup && make build-image
```

**Si no tienes make:**

```bash
# Paso a paso
docker-compose build --no-cache
docker-compose up -d
docker-compose exec builder /entrypoint.sh init
docker-compose exec builder /yocto/scripts/build-image-qwen.sh
```

---

## 🆘 Si Algo Falla

### Error: "Disk space is full"
```bash
# Ver espacio
docker-compose exec builder df -h /yocto

# Aumentar espacio en host y reintentar
# O limpiar descargas antiguas
docker-compose exec builder find /yocto/dl -type f -mtime +30 -delete
```

### Error: "License agreement not accepted"
```bash
# Entrar al contenedor
docker-compose exec builder bash

# Editar local.conf
echo 'LICENSE_FLAGS_ACCEPTED = "nvidia-tegra"' >> /yocto/build/conf/local.conf

# Reintentear
make build-image
```

### El build se congela
```bash
# Detener gracefully
docker-compose stop --time=30

# O matar
docker-compose kill

# Limpiar y reintentar
make clean-build
make build-image
```

### Ver todos los logs de error
```bash
docker-compose exec builder \
  grep -i error /yocto/build/tmp/log.do_build | tail -20
```

---

## 📚 Documentación Disponible

En la carpeta descargas tienes:

| Archivo | Para qué |
|---------|----------|
| `Dockerfile` | Imagen base del contenedor |
| `docker-compose.yml` | Configuración del servicio |
| `docker-entrypoint.sh` | Script de inicialización automática |
| `Makefile` | Comandos útiles (make build, etc.) |
| `.dockerignore` | Archivos a excluir del build |
| `.env.example` | Variables de entorno (copiar a .env si necesitas personalizar) |
| `DOCKER_GUIA.md` | Guía completa del contenedor (leyendo opcional) |
| `YOCTO_QWEN_ADAPTACION.md` | Detalles técnicos de la migración Ollama→Qwen |
| `GUIA_RAPIDA_QWEN.md` | Comparativa y troubleshooting |
| `migrate-to-qwen.sh` | Script para adaptar repo original |

---

## 🎓 Explicación del Proceso

### ¿Qué hace el contenedor Docker?

1. **Provee ambiente limpio**: Ubuntu 22.04 + todas las herramientas
2. **Aísla del host**: No ensucia tu computadora
3. **Reproducibilidad**: Mismo resultado en cualquier máquina
4. **Persistencia**: Los builds se guardan en `volumes/`

### ¿Qué hace `/entrypoint.sh init`?

1. Descarga capas Yocto (~20GB) 📦
2. Configura BitBake
3. Crea configuraciones (local.conf, bblayers.conf)
4. ¡Listo para compilar!

### ¿Qué hace `bitbake jetson-nano-qwen-image`?

1. Descarga código fuente de paquetes (~30GB)
2. Compila para arquitectura aarch64 (ARM)
3. Optimiza para Jetson Nano
4. Incluye Qwen LLM + servicios
5. Genera imagen flasheable

---

## ⏱️ Línea de Tiempo

```
t=0min    → docker-compose build   ✅ 10-15 minutos
t=20min   → docker-compose up      ✅ <1 minuto
t=20min   → /entrypoint.sh init    ✅ 15-20 minutos
t=40min   → bitbake image          ✅ 6-12 horas
t=480min+ → imagen lista!          ✅ En output/
```

**Mientras compila**:
- Puedes trabajar en tu computadora
- Monitorea ocasionalmente
- ☕ Tómate un café

---

## 🏁 Cuando Esté Listo

La imagen compilada estará en:

```
./output/jetson-nano-devkit/
├── jetson-nano-qwen-image-jetson-nano-devkit.tegraflash.tar.gz
├── jetson-nano-qwen-image-jetson-nano-devkit.tar.gz
└── other files...
```

Puedes:
1. **Flashear en Jetson Nano**: `./flash.sh jetson-nano-devkit mmcblk0p1`
2. **Archivar**: Guardar en disco/nube para futuro
3. **Compartir**: Enviar a colegas

---

## 🎉 ¡Listo!

Ahora tienes un **contenedor Docker reproducible** que compila imágenes Yocto con **Qwen LLM** para **Jetson Nano**.

¿Preguntas? Revisa:
- `DOCKER_GUIA.md` - Detalles completos
- `GUIA_RAPIDA_QWEN.md` - Problemas y soluciones

**¡A compilar!** 🚀
