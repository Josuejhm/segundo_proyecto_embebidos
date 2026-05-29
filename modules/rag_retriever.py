"""
modules/rag_retriever.py
------------------------
Módulo de Recuperación Aumentada por Generación (RAG) — backend TF-IDF offline.

CAMBIOS EN ESTA VERSIÓN (adaptación Jetson 2 GB):

1. n=1 POR DEFECTO en retrieve() y retrieve_para_modo():
   - Razón: con qwen2.5:3b Q3_K_M y num_ctx=512, cada fragmento RAG
     agrega ~37 tokens al prompt. Con n=2 el prompt puede superar los
     220 tokens seguros y presionar el KV-cache.
   - En PC de desarrollo se puede pasar n=2 explícitamente.

2. UMBRAL DE SIMILITUD AJUSTADO (0.03 → sin cambios):
   - TF-IDF sobre corpus pequeño produce scores 0.05-0.20.
   - El umbral 0.03 es correcto y no se toca.

BACKEND:
  sklearn.TfidfVectorizer + numpy (sin embeddings neuronales).
  El índice (docs.json, embeddings.npy, vectorizer.pkl) se construye
  una vez en PC con scripts/build_rag_index.py.
"""

import json
import logging
import os
import pickle
from typing import Optional

import numpy as np
from sklearn.preprocessing import normalize

logger = logging.getLogger(__name__)

RAG_INDEX_PATH = "rag/index"
DOCS_FILENAME  = "docs.json"
EMB_FILENAME   = "embeddings.npy"
VECT_FILENAME  = "vectorizer.pkl"

SIM_THRESHOLD = 0.03

QUERIES_POR_MODO = {
    "diagnostico_fitosanitario": (
        "enfermedades papa síntomas hojas manchas tizón fusariosis Costa Rica"
    ),
    "riego_fertilizacion": (
        "riego fertilización papa humedad suelo nitrógeno potasio fósforo Cartago"
    ),
    "economia": (
        "precios papa PIMA Costa Rica colones calidad primera segunda tercera rentabilidad"
    ),
}


class RAGRetriever:
    """
    Recuperador de contexto RAG — backend TF-IDF + similitud coseno.
    Diseñado para funcionar completamente offline en ARM64 (Jetson Nano B01).
    """

    def __init__(
        self,
        index_path: str = RAG_INDEX_PATH,
        model_name: str = "",   # Ignorado en este backend, solo por compatibilidad
    ):
        self._index_path = index_path
        self._docs: list       = []
        self._embeddings       = None
        self._vectorizer       = None
        self._disponible       = False
        self._intentar_inicializar()

    # ── Inicialización ────────────────────────────────────────────────────────

    def _intentar_inicializar(self) -> None:
        docs_path  = os.path.join(self._index_path, DOCS_FILENAME)
        emb_path   = os.path.join(self._index_path, EMB_FILENAME)
        vect_path  = os.path.join(self._index_path, VECT_FILENAME)

        faltantes = [p for p in (docs_path, emb_path, vect_path)
                     if not os.path.exists(p)]
        if faltantes:
            logger.warning(
                "Índice RAG incompleto en '%s'. Archivos faltantes: %s\n"
                "  → Ejecutar: python3 scripts/build_rag_index.py",
                self._index_path,
                ", ".join(os.path.basename(p) for p in faltantes),
            )
            return

        try:
            with open(docs_path, encoding="utf-8") as f:
                self._docs = json.load(f)

            self._embeddings = np.load(emb_path).astype(np.float32)

            with open(vect_path, "rb") as f:
                self._vectorizer = pickle.load(f)

            self._disponible = True
            logger.info(
                "RAG inicializado: %d chunks | vocab=%d | RAM=%.1f MB",
                len(self._docs),
                self._embeddings.shape[1],
                self._embeddings.nbytes / 1024 / 1024,
            )

        except Exception as e:
            logger.warning("RAG falló al inicializar: %s", e)
            self._disponible = False

    # ── API pública ───────────────────────────────────────────────────────────

    @property
    def disponible(self) -> bool:
        return self._disponible

    def retrieve(self, query: str, n: int = 1) -> list:
        """
        Recupera los n fragmentos más relevantes para la consulta.

        Args:
            query: Texto de la consulta del agricultor.
            n:     Número máximo de fragmentos (default=1 para Jetson 2 GB).
                   Pasar n=2 desde main.py si el entorno tiene más RAM.

        Returns:
            Lista de dicts con claves: id, fuente, seccion, texto.
            Lista vacía si el RAG no está disponible o no hay resultados.
        """
        if not self._disponible:
            return []

        try:
            q_sparse = self._vectorizer.transform([query])
            q_norm   = normalize(q_sparse, norm="l2").toarray().astype(np.float32)
            scores   = (self._embeddings @ q_norm.T).flatten()

            top_idx    = scores.argsort()[::-1][:n]
            fragmentos = [
                dict(self._docs[i])
                for i in top_idx
                if scores[i] >= SIM_THRESHOLD
            ]

            logger.info(
                "RAG: %d/%d fragmentos (threshold=%.2f) para '%.40s...'",
                len(fragmentos), n, SIM_THRESHOLD, query,
            )
            return fragmentos

        except Exception as e:
            logger.error("Error en RAG.retrieve(): %s", e)
            return []

    def retrieve_para_modo(
        self,
        modo:        str,
        datos_extra: Optional[str] = None,
    ) -> list:
        """
        Construye automáticamente la query de recuperación según el modo activo.

        Args:
            modo:        diagnostico_fitosanitario | riego_fertilizacion | economia
            datos_extra: Texto adicional para enriquecer la query.

        Returns:
            Lista de fragmentos relevantes (mismo formato que retrieve()).
        """
        query = QUERIES_POR_MODO.get(modo, "cultivo papa Costa Rica")
        if datos_extra and datos_extra.strip():
            query = f"{query} {datos_extra.strip()}"
        # n=1: seguro para Jetson 2 GB
        return self.retrieve(query, n=1)