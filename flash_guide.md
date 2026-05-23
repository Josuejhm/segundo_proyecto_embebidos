# Flashear imagen Yocto en Jetson Nano (P3541)

Imagen: `jetson-nano-qwen-image.ext4`  
Script principal: `dosdcard.sh`  
SD recomendada: ≥32GB, clase U3/V30  
Lector recomendado: USB 3.0

---

## 1. Preparación

### Identificar el device de la SD
```bash
lsblk
```
Busca tu SD por tamaño (ej. `/dev/sdb`). **Verifica bien antes de continuar — un device equivocado puede destruir el disco del host.**

### Deshabilitar suspensión (evita interrupciones durante el flash)
```bash
sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
```
Revertir al terminar:
```bash
sudo systemctl unmask sleep.target suspend.target hibernate.target hybrid-sleep.target
```

---

## 2. Limpiar la SD

```bash
sudo wipefs -a /dev/sdX
sudo sgdisk --zap-all /dev/sdX
```

> Si `sgdisk` no está instalado: `sudo apt install gdisk`

---

## 3. Flashear la SD

Desde la carpeta donde se extrajo el `.tar.gz`:

```bash
cd ~/ruta-a-la-carpeta-extraida/
sudo ./dosdcard.sh /dev/sdX
```

El proceso no muestra barra de progreso. Usa los comandos de monitoreo de la sección 4 en otra terminal.

---

## 4. Monitorear el progreso

### Ver actividad de escritura en tiempo real
En otra terminal, mientras corre el flash:

```bash
watch -n 1 "iostat -d sdX"
```

Muestra KB escritos cada 1 segundo. Valores normales esperados con USB 3.0 + SD U3: **5,000–20,000 kB/s**. Valores por debajo de 1,000 kB/s indican un problema de hardware (lector lento o SD de baja calidad).

### Ver bytes escritos acumulados (si el proceso usa `dd`)
```bash
watch -n 5 "cat /proc/\$(pgrep -n dd)/fdinfo/1 2>/dev/null | grep pos"
```

El campo `pos` muestra bytes escritos. Tamaño total de la imagen: **15,032,385,536 bytes**.

---

## 5. Cancelar el proceso (si es necesario)

```bash
sudo kill -9 $(pgrep -f dosdcard)
```

Luego limpiar la SD antes de reintentar (ver sección 2).

---

## Anexo — Generar un `.img` para flashear con Balena Etcher

Si se prefiere usar Balena Etcher en lugar de flashear directo a la SD, se puede generar un archivo `.img` completo:

```bash
cd ~/ruta-a-la-carpeta-extraida/
sudo ./dosdcard.sh ~/jetson-nano.img
```

Esto escribe la imagen a un archivo en lugar de a un device. El archivo resultará en ~15GB, así que verifica espacio disponible antes:

```bash
df -h ~
```

Una vez generado el `.img`, ábrelo con Balena Etcher normalmente.

> **Nota:** Balena escribirá a la misma velocidad que el método por terminal si el lector o la SD son lentos. El cuello de botella es siempre el hardware.

---

## Notas importantes

- Una vez flasheada la SD, insertarla en el Jetson Nano y encender. No se requiere cable USB ni recovery mode para el boot desde SD.
- Si el Jetson no arranca, es posible que el SPI flash tenga un bootloader incompatible con el layout de Yocto y se requiera un flash por USB-C previo.