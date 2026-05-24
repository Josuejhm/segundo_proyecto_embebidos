"""
scripts/export_to_onnx.py
--------------------------
Exporta el modelo PyTorch a ONNX para deployment en Jetson Nano.

POR QUÉ ONNX Y NO PYTORCH DIRECTO:
────────────────────────────────────
1. onnxruntime-gpu soporta CUDA 10.2 (requerido por Maxwell/JetPack 4.6.x).
   PyTorch para ARM64 + CUDA 10.2 es muy difícil de instalar en Yocto.

2. El modelo ONNX es ~14 MB vs ~14 MB PyTorch, tamaño idéntico, pero
   onnxruntime tiene mejor soporte de recetas Yocto que torch completo.

3. Path futuro a TensorRT: ONNX → trtexec → engine .trt (40-80 ms/img).
   Reemplaza CUDAExecutionProvider si se necesita latencia ≤5 segundos.

4. Portabilidad: mismo archivo binario en PC (pruebas) y Jetson (producción).

RUTA DE OPTIMIZACIÓN EN JETSON:
ONNX (hoy) → onnxruntime CUDA EP (80-200 ms) → TensorRT (40-80 ms)
"""

import json
import torch
import onnx
import onnxruntime as ort
import numpy as np
from pathlib import Path
from torchvision import models
import torch.nn as nn

MODEL_DIR   = Path("data/models")
MODEL_NAME  = "mobilenetv2_potato"
CLASSES     = ["Potato___Early_blight", "Potato___Late_blight", "Potato___healthy"]
IMG_SIZE    = 224
DEVICE      = torch.device("cpu")  # Export siempre en CPU


def rebuild_model():
    """Reconstruye la arquitectura exacta usada en entrenamiento."""
    model = models.mobilenet_v2(weights=None)
    in_features = model.classifier[1].in_features
    model.classifier = nn.Sequential(
        nn.Dropout(p=0.3),
        nn.Linear(in_features, 128),
        nn.ReLU(inplace=True),
        nn.Dropout(p=0.2),
        nn.Linear(128, len(CLASSES)),
    )
    return model


def main():
    pth_path  = MODEL_DIR / f"{MODEL_NAME}_best.pth"
    onnx_path = MODEL_DIR / f"{MODEL_NAME}.onnx"

    if not pth_path.exists():
        print(f"ERROR: {pth_path} no encontrado.")
        print("Ejecutar primero: python scripts/train_mobilenet.py")
        return

    # Cargar pesos
    model = rebuild_model().to(DEVICE)
    state = torch.load(pth_path, map_location=DEVICE)
    model.load_state_dict(state)
    model.eval()

    # Tensor dummy para export (batch=1, C=3, H=224, W=224)
    dummy = torch.randn(1, 3, IMG_SIZE, IMG_SIZE).to(DEVICE)

    # Export a ONNX con opset 12 (compatible con onnxruntime 1.8+ y CUDA 10.2 EP)
    print(f"Exportando a {onnx_path} ...")
    torch.onnx.export(
        model,
        dummy,
        str(onnx_path),
        export_params=True,
        opset_version=12,
        do_constant_folding=True,
        input_names=["image"],
        output_names=["logits"],
        dynamic_axes={
            "image":  {0: "batch_size"},
            "logits": {0: "batch_size"},
        },
    )

    # Verificar integridad del grafo ONNX
    onnx_model = onnx.load(str(onnx_path))
    onnx.checker.check_model(onnx_model)
    print("✓ Grafo ONNX válido")

    # Verificar inferencia con onnxruntime (CPU EP, sin CUDA)
    session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    input_np = dummy.numpy()
    out = session.run(None, {"image": input_np})
    logits = out[0][0]
    probs  = _softmax(logits)
    pred   = int(np.argmax(probs))
    print(f"✓ Inferencia onnxruntime OK: {CLASSES[pred]} ({probs[pred]*100:.1f}%) [dummy input]")

    # Tamaño del archivo
    size_mb = onnx_path.stat().st_size / 1_048_576
    print(f"✓ Tamaño ONNX: {size_mb:.1f} MB")

    # Benchmark latencia CPU (referencia para estimar Jetson)
    import time
    N_RUNS = 50
    times = []
    for _ in range(N_RUNS):
        t0 = time.perf_counter()
        session.run(None, {"image": input_np})
        times.append((time.perf_counter() - t0) * 1000)

    avg_ms = sum(times) / N_RUNS
    p95_ms = sorted(times)[int(N_RUNS * 0.95)]

    print(f"\n— Benchmark latencia CPU (x86) —")
    print(f"  Promedio: {avg_ms:.1f} ms")
    print(f"  P95:      {p95_ms:.1f} ms")
    print(f"\n— Estimación Jetson Nano —")
    print(f"  CPU ARM (sin GPU):    {avg_ms * 3.5:.0f} ms  (factor ×3.5 conservador)")
    print(f"  GPU Maxwell CUDA 10.2: {avg_ms * 0.6:.0f} ms  (factor ×0.6 estimado)")
    print(f"  TensorRT 8.x (futuro): {avg_ms * 0.3:.0f} ms  (factor ×0.3 estimado)")

    print(f"\nModelo listo: {onnx_path}")
    print("Copiar a Jetson Nano: scp data/models/mobilenetv2_potato.onnx user@jetson:/data/models/")

    # Instrucciones TensorRT (para optimización futura)
    print("\n— Conversión a TensorRT (opcional, en el Jetson) —")
    print("  trtexec --onnx=mobilenetv2_potato.onnx \\")
    print("          --saveEngine=mobilenetv2_potato.trt \\")
    print("          --fp16 --workspace=256")


def _softmax(x):
    e = np.exp(x - np.max(x))
    return e / e.sum()


if __name__ == "__main__":
    main()
