"""
modules/vision_classifier.py
-----------------------------
Clasificador de enfermedades de papa usando MobileNetV2 + ONNX Runtime.

DECISION DE DISEÑO:
- Modelo: MobileNetV2 fine-tuned sobre PlantVillage (subconjunto papa, 3 clases)
- Formato: ONNX (portable entre PC x86 y Jetson ARM64)
- Inferencia: onnxruntime-gpu con CUDA 10.2 EP en Jetson / CPU EP en desarrollo
- RAM del modelo: ~14 MB (ONNX) vs ~2 GB de un VLM multimodal → decisión correcta
- Precisión esperada: ≥90% en condiciones de campo (PlantVillage + data augmentation)

CLASES (subconjunto papa de PlantVillage):
  0 → Potato___Early_blight     (Alternaria solani)
  1 → Potato___Late_blight      (Phytophthora infestans — tizón tardío)
  2 → Potato___healthy          (planta sana)

PIPELINE:
  Cámara CSI → OpenCV preprocess → MobileNetV2 ONNX → clase + confianza
  → descripción texto → contexto LLM (qwen2.5:3b via Ollama)
"""

import cv2
import numpy as np
import onnxruntime as ort
import time
import os
import logging
from pathlib import Path
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ── Constantes ────────────────────────────────────────────────────────────────

MODEL_PATH = Path(os.environ.get("VISION_MODEL_PATH", "data/models/mobilenetv2_potato.onnx"))
IMG_SIZE = (224, 224)   # MobileNetV2 standard input
CONF_THRESHOLD = 0.60   # Umbral mínimo de confianza para diagnóstico

CLASSES = [
    "Potato___Early_blight",
    "Potato___Late_blight",
    "Potato___healthy",
]

# Nombres en español para el LLM
CLASES_ES = {
    "Potato___Early_blight": "tizón temprano (Alternaria solani)",
    "Potato___Late_blight":  "tizón tardío (Phytophthora infestans)",
    "Potato___healthy":      "planta sana",
}

# Severidad por clase (para priorización de respuesta)
SEVERIDAD = {
    "Potato___Late_blight":  "CRÍTICA",  # puede destruir cosecha en 72h
    "Potato___Early_blight": "MODERADA",
    "Potato___healthy":      "NINGUNA",
}


@dataclass
class ResultadoVision:
    clase_raw: str
    clase_es: str
    confianza: float
    severidad: str
    descripcion_llm: str
    tiempo_inferencia_ms: float
    imagen_guardada: str | None


# ── Clasificador principal ─────────────────────────────────────────────────────

class ClasificadorPapa:
    """
    Inferencia con MobileNetV2 ONNX.

    En desarrollo (PC x86):
        - Usa CPUExecutionProvider automáticamente
        - Mide latencia real de CPU → escala ×3-5 para estimar Jetson CPU

    En Jetson Nano (ARM64 + CUDA 10.2):
        - Usa CUDAExecutionProvider (Maxwell, CUDA 10.2)
        - Latencia real en Maxwell ≈ 80-200 ms por imagen
    """

    def __init__(self):
        self._session = None
        self._disponible = False
        self._proveedor = "desconocido"
        self._inicializar()

    def _inicializar(self):
        if not MODEL_PATH.exists():
            logger.warning(
                "Modelo ONNX no encontrado en %s. "
                "Ejecutar: python scripts/train_mobilenet.py && python scripts/export_to_onnx.py",
                MODEL_PATH,
            )
            return

        # Selección automática de proveedor: CUDA si disponible, CPU como fallback
        providers_disponibles = ort.get_available_providers()
        logger.info("ONNX RT providers disponibles: %s", providers_disponibles)

        if "CUDAExecutionProvider" in providers_disponibles:
            # Jetson Nano: CUDA 10.2 con Maxwell
            opts = ort.SessionOptions()
            opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            self._session = ort.InferenceSession(
                str(MODEL_PATH),
                sess_options=opts,
                providers=[
                    ("CUDAExecutionProvider", {"device_id": 0, "cudnn_conv_algo_search": "DEFAULT"}),
                    "CPUExecutionProvider",
                ],
            )
            self._proveedor = "CUDA (Maxwell)"
        else:
            # PC de desarrollo: solo CPU
            self._session = ort.InferenceSession(
                str(MODEL_PATH),
                providers=["CPUExecutionProvider"],
            )
            self._proveedor = "CPU (desarrollo)"

        self._disponible = True
        logger.info("ClasificadorPapa listo — proveedor: %s", self._proveedor)

    @property
    def disponible(self) -> bool:
        return self._disponible

    # ── Captura de cámara ──────────────────────────────────────────────────────

    def _abrir_camara(self):
        """
        Abre la cámara CSI en Jetson (GStreamer) o USB en desarrollo.
        La variable CAMERA_SOURCE permite override para testing.
        """
        source = os.environ.get("CAMERA_SOURCE", "auto")

        if source == "auto":
            # Intenta CSI (Jetson) primero, cae a USB si falla
            gst = (
                "nvarguscamerasrc ! "
                "video/x-raw(memory:NVMM), width=1280, height=720, framerate=30/1 ! "
                "nvvidconv ! video/x-raw, format=BGRx ! "
                "videoconvert ! video/x-raw, format=BGR ! appsink"
            )
            cap = cv2.VideoCapture(gst, cv2.CAP_GSTREAMER)
            if not cap.isOpened():
                logger.info("CSI no disponible, usando cámara USB 0")
                cap = cv2.VideoCapture(0)
        elif source.isdigit():
            cap = cv2.VideoCapture(int(source))
        else:
            cap = cv2.VideoCapture(source)  # archivo de video o URL

        return cap

    # ── Preprocesamiento ───────────────────────────────────────────────────────

    @staticmethod
    def _preprocess(frame: np.ndarray) -> np.ndarray:
        """
        Preprocesamiento estándar MobileNetV2 (ImageNet normalization).
        Identical al usado durante el entrenamiento con PlantVillage.
        """
        img = cv2.resize(frame, IMG_SIZE)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = img.astype(np.float32) / 255.0
        # Normalización ImageNet: mean=[0.485,0.456,0.406], std=[0.229,0.224,0.225]
        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        std  = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        img = (img - mean) / std
        img = np.transpose(img, (2, 0, 1))  # HWC → CHW
        img = np.expand_dims(img, axis=0)   # batch=1
        return img

    # ── Análisis complementario OpenCV ────────────────────────────────────────

    @staticmethod
    def _analisis_hsv(frame: np.ndarray) -> dict:
        """
        Análisis HSV complementario al CNN — aporta métricas cuantitativas
        al contexto del LLM (% área afectada, tono dominante).

        RAZÓN DE EXISTENCIA: El CNN clasifica la clase de enfermedad,
        pero no cuantifica el porcentaje de área foliar afectada.
        Esta métrica es crucial para la recomendación agronómica.
        """
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        total_px = frame.shape[0] * frame.shape[1]

        # Tejido necrótico / lesiones oscuras
        mask_necro = cv2.inRange(hsv, (0, 0, 0), (180, 255, 55))
        pct_necro = (np.sum(mask_necro > 0) / total_px) * 100

        # Clorosis (amarillamiento)
        mask_yellow = cv2.inRange(hsv, (18, 60, 80), (38, 255, 255))
        pct_yellow = (np.sum(mask_yellow > 0) / total_px) * 100

        # Verde sano dominante
        mask_green = cv2.inRange(hsv, (35, 40, 40), (85, 255, 255))
        pct_green = (np.sum(mask_green > 0) / total_px) * 100

        return {
            "pct_necrosis": round(pct_necro, 1),
            "pct_clorosis": round(pct_yellow, 1),
            "pct_verde_sano": round(pct_green, 1),
        }

    # ── Inferencia principal ───────────────────────────────────────────────────

    def analizar(self, imagen_path: str | None = None) -> ResultadoVision:
        """
        Captura o carga imagen, clasifica, devuelve ResultadoVision.

        Args:
            imagen_path: Si se provee, usa esta imagen en vez de cámara.
                         Útil para testing y procesamiento batch.
        """
        if not self._disponible:
            return ResultadoVision(
                clase_raw="error", clase_es="modelo no disponible",
                confianza=0.0, severidad="DESCONOCIDA",
                descripcion_llm="Sistema de visión no disponible. Describe verbalmente los síntomas.",
                tiempo_inferencia_ms=0.0, imagen_guardada=None,
            )

        # Obtener frame
        if imagen_path:
            frame = cv2.imread(imagen_path)
            if frame is None:
                raise ValueError(f"No se pudo cargar imagen: {imagen_path}")
        else:
            cap = self._abrir_camara()
            ret, frame = cap.read()
            cap.release()
            if not ret:
                raise RuntimeError("No se pudo capturar frame de la cámara")

        # Guardar captura reducida para log/reporte
        save_path = None
        os.makedirs("data/images", exist_ok=True)
        ts = int(time.time())
        save_path = f"data/images/cap_{ts}.jpg"
        small = cv2.resize(frame, (320, 240))
        cv2.imwrite(save_path, small)

        # Inferencia CNN
        input_tensor = self._preprocess(frame)
        input_name = self._session.get_inputs()[0].name

        t0 = time.perf_counter()
        outputs = self._session.run(None, {input_name: input_tensor})
        t1 = time.perf_counter()
        inference_ms = (t1 - t0) * 1000

        logits = outputs[0][0]  # shape: (3,)
        probs = _softmax(logits)
        idx = int(np.argmax(probs))
        confianza = float(probs[idx])
        clase_raw = CLASSES[idx] if confianza >= CONF_THRESHOLD else "baja_confianza"
        clase_es = CLASES_ES.get(clase_raw, "no determinado")
        severidad = SEVERIDAD.get(clase_raw, "DESCONOCIDA")

        # Análisis HSV complementario
        hsv_data = self._analisis_hsv(frame)

        # Construir descripción para el LLM
        descripcion = self._build_contexto_llm(
            clase_raw, clase_es, confianza, severidad, hsv_data
        )

        logger.info(
            "Visión: %s (%.1f%%) | necro=%.1f%% | %.0f ms | %s",
            clase_es, confianza * 100,
            hsv_data["pct_necrosis"], inference_ms, self._proveedor,
        )

        return ResultadoVision(
            clase_raw=clase_raw,
            clase_es=clase_es,
            confianza=confianza,
            severidad=severidad,
            descripcion_llm=descripcion,
            tiempo_inferencia_ms=inference_ms,
            imagen_guardada=save_path,
        )

    @staticmethod
    def _build_contexto_llm(clase_raw, clase_es, confianza, severidad, hsv) -> str:
        """
        Transforma el resultado de visión en texto estructurado para el prompt LLM.
        El LLM recibe TEXTO, no imagen — por eso esta función es crítica.
        """
        if clase_raw == "baja_confianza":
            return (
                f"El análisis visual no fue concluyente (confianza insuficiente). "
                f"Se observa: necrosis en {hsv['pct_necrosis']}% del área foliar, "
                f"clorosis en {hsv['pct_clorosis']}%, tejido verde sano en {hsv['pct_verde_sano']}%. "
                "Requiere inspección más detallada."
            )

        base = (
            f"Diagnóstico de visión computacional: {clase_es} "
            f"(confianza {confianza*100:.1f}%, severidad {severidad}). "
            f"Métricas foliares: necrosis {hsv['pct_necrosis']}%, "
            f"clorosis {hsv['pct_clorosis']}%, tejido sano {hsv['pct_verde_sano']}%."
        )

        if clase_raw == "Potato___Late_blight" and hsv["pct_necrosis"] > 10:
            base += (
                " ALERTA: El tizón tardío con este porcentaje de necrosis "
                "puede devastar la cosecha en 48-72 horas bajo condiciones de humedad."
            )

        return base


# ── Utilidades ────────────────────────────────────────────────────────────────

def _softmax(x: np.ndarray) -> np.ndarray:
    e = np.exp(x - np.max(x))
    return e / e.sum()
