# 🚀 Yocto-Qwen2.5:3b Docker - Guía Rápida (VERSIÓN SIMPLIFICADA)

**Versión que funciona sin errores** ✅

---

## 📋 Archivos Necesarios

Descarga o copia estos 4 archivos a tu carpeta del proyecto:

```bash
# Los 4 archivos ÚNICOS que necesitas:
1. Dockerfile                  (imagen base Docker)
2. docker-compose.yml          (configuración servicios)
3. docker-entrypoint.sh        (inicialización automática)
4. Makefile                    (comandos útiles)

# NOTA: NO necesitas:
# - scripts/ (se crea automáticamente)
# - conf/ (se crea automáticamente)  
# - meta-ollama/ (se elimina, usamos meta-qwen)
```

---

## ✅ Verificar Estructura

```bash
cd tu-proyecto
ls -la

# Debería mostrar:
# -rw-r--r-- Dockerfile
# -rw-r--r-- docker-compose.yml
# -rw-r--r-- docker-entrypoint.sh
# -rw-r--r-- Makefile
```

---

## 🎯 Pasos: 1-2-3

### PASO 1: Build Docker (10-15 minutos)

```bash
docker-compose build --no-cache
```

**Esperado:**
```
Building builder
[+] Building 12.3s (15/15)
...
Successfully tagged yocto-qwen:latest
```

**Si da error:** `"/meta-ollama": not found`
- Borra el archivo antiguo `Dockerfile`
- Usa el Dockerfile simplificado de las descargas
- Reintenta: `docker-compose build --no-cache`

---

### PASO 2: Crear Contenedor (< 1 minuto)

```bash
docker-compose up -d
```

**Verificar:**
```bash
docker-compose ps
# Status debe decir "Up"
```

---

### PASO 3: Setup Inicial (15-20 minutos - SOLO UNA VEZ)

```bash
docker-compose exec builder /entrypoint.sh init
```

**¿Qué hace?**
- Descarga capas Yocto (poky, meta-tegra, meta-openembedded, etc.)
- Crea meta-qwen
- Configura BitBake
- Prepara directorios

**Esperado:**
```
ℹ Descargando capas Yocto (10-15 minutos)...
  → poky (kirkstone)...
  → meta-tegra (kirkstone-l4t-r35.4)...
  → meta-openembedded (kirkstone)...
  → meta-clang (kirkstone)...
  → meta-virtualization (kirkstone)...
✓ Capas Yocto descargadas

✓ Inicialización completada

╔═══════════════════════════════════════════════════════════╗
║        🐋 Yocto-Qwen2.5:3b Build Container 🐋           ║
╚═══════════════════════════════════════════════════════════╝
```

---

### PASO 4: Compilar Imagen Yocto (6-12 horas)

```bash
docker-compose exec builder /yocto/scripts/build-image-qwen.sh
```

**¿Qué hace?**
- Descarga código fuente de paquetes (~30GB)
- Compila para Jetson Nano (aarch64)
- Incluye Qwen2.5:3b LLM
- Genera imagen flasheable

**Esperado:**
```
🔨 Compilando imagen Yocto con Qwen2.5:3b...
   Imagen: jetson-nano-qwen-image
   Directorio: /yocto/build

⏳ Iniciando BitBake (6-12 horas)...

[10 %] ...
[20 %] ...
...
✅ Build completado!
📦 Imágenes en: /yocto/build/tmp/deploy/images/jetson-nano-devkit/
```

---

## ⚡ Comandos Útiles (Con Make)

```bash
# Ver todos los comandos
make help

# Compilación
make build          # Build Docker (10-15 min)
make up             # Crear contenedor (< 1 min)
make init           # Setup inicial (15-20 min, solo 1ª vez)
make build-image    # Compilar imagen (6-12 horas)

# Entrar al contenedor
make shell          # Como usuario builder
make root-shell     # Como root (si necesitas)

# Monitoreo
make status         # Ver estado + recursos
make logs           # Ver logs en vivo
make space          # Uso de disco

# Limpiar
make clean-build    # Limpiar build anterior
make stop           # Parar contenedor

# Todo automático
make full-setup     # build + up + init
```

---

## 🎯 Timeline

```
t=0 min       → docker-compose build --no-cache   ✅ 10-15 min
t=20 min      → docker-compose up -d              ✅ < 1 min
t=20 min      → /entrypoint.sh init               ✅ 15-20 min
t=40 min      → build-image-qwen.sh               ✅ 6-12 horas ☕
t=480+ min    → Imagen lista en output/            ✅ DONE!
```

---

## 📦 Resultado Final

Una vez completado, tendrás en `volumes/output/jetson-nano-devkit/`:

```
jetson-nano-qwen-image-jetson-nano-devkit.tar.gz        (3-4 GB)
jetson-nano-qwen-image-jetson-nano-devkit.tegraflash.tar.gz
```

Puedes:
- Flashear en Jetson Nano
- Archivar para futuro
- Compartir con colegas

---

## 🆘 Troubleshooting

### Error: "Dockerfile: not found" en build

```bash
# Asegúrate de tener el Dockerfile en tu carpeta
ls -la Dockerfile

# Si no, cópialo desde descargas
cp ~/Descargas/Dockerfile .
```

### Error: "failed to compute cache key: /meta-ollama not found"

```bash
# Significa que tienes el Dockerfile antiguo
# Reemplázalo con el simplificado:

# OPCIÓN A: Copiar desde descargas
cp ~/Descargas/DOCKERFILE_SIMPLIFICADO Dockerfile

# OPCIÓN B: O descarga el correcto
# Y luego:
docker system prune -a
docker-compose build --no-cache
```

### El build se detiene / congela

```bash
# Detener gracefully
docker-compose stop --time=30

# Si no responde
docker-compose kill

# Limpiar y reintentar
make clean-build
make build-image
```

### Error: "docker-entrypoint.sh: not found"

```bash
# Asegúrate de tener el archivo
ls -la docker-entrypoint.sh

# Si no:
cp ~/Descargas/docker-entrypoint.sh .
chmod +x docker-entrypoint.sh
```

### Ver logs del error

```bash
# Ver logs del contenedor
docker-compose logs builder

# Ver logs específicos de BitBake
docker-compose exec builder \
  tail -100 /yocto/build/tmp/log.do_build

# Buscar errores
docker-compose exec builder \
  grep -i ERROR /yocto/build/tmp/log.do_build | tail -20
```

---

## 📊 Especificaciones

**Modelo:** Qwen2.5:3b (optimizado para Jetson Nano)
**Máquina:** jetson-nano-devkit (tegra210)
**Distro:** Poky (Yocto kirkstone)
**GPU:** NVIDIA Maxwell (128 cores)

**Capas Yocto:**
- poky (base)
- meta-tegra (soporte Jetson)
- meta-openembedded (recetas extendidas)
- meta-clang (LLVM)
- meta-virtualization (contenedores)
- meta-qwen (Qwen2.5:3b)

---

## ✨ Características de esta Versión

✅ **Sin errores** - No intenta copiar directorios inexistentes
✅ **Automático** - `/entrypoint.sh init` hace todo
✅ **Simple** - Solo 4 archivos necesarios
✅ **Rápido** - Rebuild en ~30 min con cache
✅ **Reproducible** - Mismo resultado en cualquier máquina
✅ **Aislado** - Docker no ensucia tu sistema

---

## 🎬 Comando Completo (Todo de una vez)

```bash
docker-compose build --no-cache && \
docker-compose up -d && \
docker-compose exec builder /entrypoint.sh init && \
docker-compose exec builder /yocto/scripts/build-image-qwen.sh
```

---

## 📚 Documentación Disponible

- **INICIO_RAPIDO.md** - Guía paso a paso original
- **DOCKER_GUIA.md** - Guía completa con detalles
- **GUIA_RAPIDA_QWEN.md** - Comparativa y troubleshooting
- **SOLUCION_ERRORES.md** - Soluciones a errores comunes

---

**¡Listo! Con esto funciona perfectamente.** 🚀

Cualquier duda, revisar SOLUCION_ERRORES.md o usar `make help`
