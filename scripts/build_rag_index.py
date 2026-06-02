#!/usr/bin/env python3
"""
build_rag_index.py — Construcción del índice RAG para AGRI-EDGE-IA
-----------------------------------------------------------------------
Estrategia: TF-IDF (sklearn) + similitud coseno (numpy)
  - Sin descargas de modelos → funciona offline en Jetson Nano
  - Ligero en RAM (~20 MB vs ~400 MB de sentence-transformers)
  - Vectores persistidos como embeddings.npy + docs.json

Salida en rag/index/:
  docs.json        — chunks de texto con metadatos
  embeddings.npy   — matriz TF-IDF (n_chunks × vocab)
  vectorizer.pkl   — vectorizador ajustado (para query-time)

Uso:
  python3 scripts/build_rag_index.py
  python3 scripts/build_rag_index.py --docs-dir rag/documentos --index-dir rag/index
"""

import argparse
import json
import os
import pickle
import re
import sys
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize


# ── Configuración de chunking ───────────────────────────────────────────────

CHUNK_SIZE = 400          # palabras por chunk (aprox 2-3 párrafos)
CHUNK_OVERLAP = 60        # palabras de solapamiento entre chunks
MIN_CHUNK_WORDS = 30      # descartar chunks muy pequeños


# ── Utilidades de texto ─────────────────────────────────────────────────────

def limpiar_markdown(texto: str) -> str:
    """Elimina sintaxis Markdown manteniendo el contenido semántico."""
    # Eliminar bloques de código
    texto = re.sub(r"```[\s\S]*?```", " ", texto)
    texto = re.sub(r"`[^`]+`", " ", texto)
    # Convertir encabezados en texto plano (conservar para búsqueda)
    texto = re.sub(r"^#{1,6}\s+", "", texto, flags=re.MULTILINE)
    # Eliminar negritas/cursivas
    texto = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", texto)
    texto = re.sub(r"_{1,3}([^_]+)_{1,3}", r"\1", texto)
    # Eliminar links pero conservar texto
    texto = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", texto)
    # Eliminar tablas (bordes)
    texto = re.sub(r"^\|[-: |]+\|$", "", texto, flags=re.MULTILINE)
    texto = re.sub(r"\|", " ", texto)
    # Limpiar espacios múltiples
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    texto = re.sub(r" {2,}", " ", texto)
    return texto.strip()


def palabras(texto: str) -> list[str]:
    return texto.split()


def chunk_por_palabras(texto: str, chunk_size: int, overlap: int) -> list[str]:
    """Divide texto en chunks de N palabras con solapamiento."""
    ws = palabras(texto)
    chunks = []
    inicio = 0
    while inicio < len(ws):
        fin = min(inicio + chunk_size, len(ws))
        chunk = " ".join(ws[inicio:fin])
        if len(palabras(chunk)) >= MIN_CHUNK_WORDS:
            chunks.append(chunk)
        inicio += chunk_size - overlap
    return chunks


def chunk_por_secciones(texto: str, chunk_size: int, overlap: int) -> list[tuple[str, str]]:
    """
    Chunking inteligente: divide en secciones Markdown primero,
    luego subdivide si la sección es muy larga.
    Retorna lista de (titulo_seccion, texto_chunk).
    """
    # Dividir por encabezados
    partes = re.split(r"(^#{1,4}\s+.+$)", texto, flags=re.MULTILINE)
    
    resultado = []
    titulo_actual = "Inicio"
    buffer = ""
    
    for parte in partes:
        if re.match(r"^#{1,4}\s+", parte):
            # Es un encabezado — vaciar buffer anterior
            if buffer.strip():
                sub = chunk_por_palabras(limpiar_markdown(buffer), chunk_size, overlap)
                for s in sub:
                    resultado.append((titulo_actual, s))
            titulo_actual = re.sub(r"^#+\s+", "", parte).strip()
            buffer = ""
        else:
            buffer += parte
    
    # Último buffer
    if buffer.strip():
        sub = chunk_por_palabras(limpiar_markdown(buffer), chunk_size, overlap)
        for s in sub:
            resultado.append((titulo_actual, s))
    
    return resultado


# ── Carga de documentos ─────────────────────────────────────────────────────

def cargar_documentos(docs_dir: Path) -> list[dict]:
    """Carga todos los .md y .txt del directorio."""
    archivos = sorted(docs_dir.glob("*.md")) + sorted(docs_dir.glob("*.txt"))
    
    if not archivos:
        print(f"  ✗ No se encontraron archivos en {docs_dir}", file=sys.stderr)
        sys.exit(1)
    
    docs = []
    for archivo in archivos:
        print(f"  Cargando: {archivo.name}")
        texto = archivo.read_text(encoding="utf-8", errors="ignore")
        chunks = chunk_por_secciones(texto, CHUNK_SIZE, CHUNK_OVERLAP)
        
        for i, (titulo, chunk_texto) in enumerate(chunks):
            if len(palabras(chunk_texto)) < MIN_CHUNK_WORDS:
                continue
            docs.append({
                "id": f"{archivo.stem}__chunk{i:03d}",
                "fuente": archivo.name,
                "seccion": titulo,
                "texto": chunk_texto,
            })
        
        print(f"    → {len(chunks)} chunks generados")
    
    return docs


# ── Construcción del índice ─────────────────────────────────────────────────

def construir_indice(docs: list[dict], index_dir: Path):
    """Ajusta TF-IDF y guarda embeddings + metadatos."""
    textos = [d["texto"] for d in docs]
    
    print(f"\n  Ajustando TF-IDF sobre {len(textos)} chunks...")
    
    vectorizer = TfidfVectorizer(
        analyzer="word",
        ngram_range=(1, 2),        # unigramas + bigramas para frases clave
        max_features=8000,         # límite de vocabulario (RAM Jetson)
        sublinear_tf=True,         # log(tf) para balancear frecuencias
        min_df=1,                  # con corpus pequeño, no filtrar
        strip_accents="unicode",
        lowercase=True,
    )
    
    matriz = vectorizer.fit_transform(textos)   # sparse (n_chunks × vocab)
    # Normalizar a longitud unitaria (cosine similarity = dot product)
    matriz_norm = normalize(matriz, norm="l2")
    embeddings = matriz_norm.toarray().astype(np.float32)
    
    print(f"  Vocabulario: {len(vectorizer.vocabulary_)} términos")
    print(f"  Matriz embeddings: {embeddings.shape} — "
          f"{embeddings.nbytes / 1024:.1f} KB en RAM")
    
    # Guardar
    index_dir.mkdir(parents=True, exist_ok=True)
    
    np_path = index_dir / "embeddings.npy"
    np.save(np_path, embeddings)
    
    docs_path = index_dir / "docs.json"
    with open(docs_path, "w", encoding="utf-8") as f:
        json.dump(docs, f, ensure_ascii=False, indent=2)
    
    vect_path = index_dir / "vectorizer.pkl"
    with open(vect_path, "wb") as f:
        pickle.dump(vectorizer, f)
    
    print(f"\n  Archivos generados en {index_dir}:")
    for p in sorted(index_dir.iterdir()):
        print(f"    {p.name:30s}  {p.stat().st_size / 1024:.1f} KB")
    
    return embeddings, vectorizer, docs


# ── Prueba de recuperación ──────────────────────────────────────────────────

def probar_query(query: str, embeddings: np.ndarray,
                 vectorizer, docs: list[dict], top_k: int = 3):
    """Recupera los top-k chunks más relevantes para una consulta."""
    q_vec = vectorizer.transform([query])
    q_norm = normalize(q_vec, norm="l2").toarray().astype(np.float32)
    scores = embeddings @ q_norm.T       # dot product = cosine (ya normalizados)
    scores = scores.flatten()
    top_idx = scores.argsort()[::-1][:top_k]
    
    print(f"\n  Query: '{query}'")
    print(f"  {'─' * 60}")
    for rank, idx in enumerate(top_idx, 1):
        doc = docs[idx]
        print(f"  [{rank}] score={scores[idx]:.3f}  {doc['fuente']}")
        print(f"      Sección: {doc['seccion']}")
        print(f"      Texto: {doc['texto'][:160].strip()}...")
        print()


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Construye índice RAG para AGRI-EDGE-IA")
    parser.add_argument("--docs-dir", default="rag/documentos",
                        help="Directorio con documentos .md/.txt")
    parser.add_argument("--index-dir", default="rag/index",
                        help="Directorio de salida del índice")
    parser.add_argument("--no-test", action="store_true",
                        help="Omitir pruebas de recuperación")
    args = parser.parse_args()
    
    docs_dir = Path(args.docs_dir)
    index_dir = Path(args.index_dir)
    
    print("=" * 65)
    print("  AGRI-EDGE-IA — Build RAG Index")
    print("=" * 65)
    print(f"\n  Documentos: {docs_dir.resolve()}")
    print(f"  Índice:     {index_dir.resolve()}\n")
    
    # 1. Cargar documentos
    print("▶ Paso 1: Cargar y chunkear documentos")
    docs = cargar_documentos(docs_dir)
    print(f"\n  Total chunks: {len(docs)}")
    
    # 2. Construir índice
    print("\n▶ Paso 2: Construir índice TF-IDF")
    embeddings, vectorizer, docs = construir_indice(docs, index_dir)
    
    # 3. Pruebas de recuperación
    if not args.no_test:
        print("\n▶ Paso 3: Pruebas de recuperación")
        queries = [
            "tizón tardío manchas hojas papa síntomas",
            "costo producción kilogramo papa precio mercado",
            "riego fertilización nitrógeno etapa fenológica",
            "almacenamiento post cosecha tuberculo calidad",
        ]
        for q in queries:
            probar_query(q, embeddings, vectorizer, docs, top_k=2)
    
    print("=" * 65)
    print("  ✓ Índice construido exitosamente")
    print("=" * 65)


if __name__ == "__main__":
    main()