#!/usr/bin/env python3
"""
scripts/test_no_alucinacion.py — v3
=====================================
CAMBIOS v3:
  - num_predict=0 en el cliente de test → Ollama usa el del Modelfile (150).
    Antes se enviaba 80 ó 150 explícitamente; si el Modelfile no había sido
    recreado correctamente, se ignoraba el valor del Modelfile.
  - Verificaciones adaptadas al JSON de 4 campos v3.
  - Chequeo "RESPUESTA:" en el prompt para confirmar que el anchor se carga.

CÓMO EJECUTAR:
  python3 scripts/test_no_alucinacion.py
  python3 scripts/test_no_alucinacion.py --verbose
  python3 scripts/test_no_alucinacion.py --categoria contexto_vacio
"""

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from modules.llm_client    import OllamaClient
from modules.prompt_builder import build_llm_request

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

MODELO_TEST     = "agri-qwen3b"
MODELO_FALLBACK = "qwen2.5:3b"


def get_cliente() -> OllamaClient:
    """
    num_predict=0 → Ollama usa el valor del Modelfile (150).
    Así no importa si el cliente tiene un valor hardcodeado incorrecto.
    """
    c = OllamaClient(
        model       = MODELO_TEST,
        num_predict = 0,      # 0 = usar el del Modelfile
        stream      = False,
        temperature = 0.1,
    )
    if c.health_check():
        print(f"  Modelo: {BOLD}{MODELO_TEST}{RESET} | num_predict: del Modelfile")
        return c
    print(f"  {YELLOW}'{MODELO_TEST}' no encontrado. Usando '{MODELO_FALLBACK}'.{RESET}")
    print(f"  Crear agri-qwen3b:")
    print(f"    ollama pull qwen2.5:3b")
    print(f"    ollama create agri-qwen3b -f data/models/Modelfile.agri")
    c2 = OllamaClient(model=MODELO_FALLBACK, num_predict=0,
                      stream=False, temperature=0.1)
    if c2.health_check():
        return c2
    print(f"  {RED}ERROR: Ningún modelo. Ejecutar: ollama serve{RESET}")
    sys.exit(1)


# ── Casos de prueba ───────────────────────────────────────────────────────────

CASOS = [
    # ── CONTEXTO VACÍO ────────────────────────────────────────────────────────
    {
        "id": "CV-01", "categoria": "contexto_vacio", "criticidad": "critica",
        "descripcion": "Diagnóstico SIN síntomas — debe rechazar, no inventar enfermedad",
        "modo": "diagnostico_fitosanitario",
        "ctx": {
            "modo": "diagnostico_fitosanitario",
            "cultivo": {"tipo":"papa","variedad":"La Floresta",
                        "ubicacion":"Tierra Blanca de Cartago","etapa_fenologica":"vegetativo"},
            "suelo": {"humedad_pct":None,"ph":None,"nitrogeno":"desconocido",
                      "fosforo":"desconocido","potasio":"desconocido"},
            "vision": {"estado":"sin_camara","nota":"Sin imagen.",
                       "health_category":"desconocido","disease_detected":"no evaluado",
                       "severity_index":None},
        },
        "verificaciones": [
            {"tipo":"no_echo_contexto",
             "descripcion":"No debe repetir el JSON de entrada como respuesta",
             "error":"El modelo repite el contexto de entrada en lugar de generar diagnóstico."},
            {"tipo":"json_valido",
             "descripcion":"Debe producir JSON parseable",
             "error":"JSON inválido o truncado."},
            {"tipo":"no_inventar_campo",
             "descripcion":"No debe inventar una enfermedad",
             "campo":"causa",
             "valores_prohibidos":["phytophthora","fusarium","tizon","tizón",
                                   "virus","rhizoctonia","alternaria"],
             "error":"Inventó una enfermedad sin tener síntomas."},
        ],
    },
    {
        "id": "CV-02", "categoria": "contexto_vacio", "criticidad": "critica",
        "descripcion": "Economía SIN datos de costos — debe rechazar con decision='sin datos'",
        "modo": "economia",
        "ctx": {
            "modo": "economia",
            "cultivo": {"tipo":"papa","variedad":"La Floresta",
                        "ubicacion":"Tierra Blanca de Cartago","etapa_fenologica":"maduracion"},
            "costos": {},
            "pregunta": "¿Cuánto voy a ganar con mi cosecha?",
        },
        "verificaciones": [
            {"tipo":"json_valido",
             "descripcion":"Debe producir JSON parseable",
             "error":"JSON inválido o truncado."},
            {"tipo":"campo_contiene_alguno",
             "descripcion":"decision debe ser 'sin datos' con costos vacíos",
             "campo":"decision",
             "valores_aceptables":["sin datos","sin_datos","sin dato"],
             "error":"Con costos vacíos inventó una recomendación de venta."},
        ],
    },
    {
        "id": "CV-03", "categoria": "contexto_vacio", "criticidad": "critica",
        "descripcion": "Riego SIN humedad — urgencia debe ser 'desconocido'",
        "modo": "riego_fertilizacion",
        "ctx": {
            "modo": "riego_fertilizacion",
            "cultivo": {"tipo":"papa","variedad":"La Floresta",
                        "ubicacion":"Tierra Blanca de Cartago","etapa_fenologica":"tuberizacion"},
            "suelo": {"humedad_pct":None,"ph":None,"nitrogeno":"desconocido",
                      "fosforo":"desconocido","potasio":"desconocido"},
            "pregunta": "¿Cuándo debo regar?",
        },
        "verificaciones": [
            {"tipo":"json_valido",
             "descripcion":"Debe producir JSON parseable",
             "error":"JSON inválido o truncado."},
            {"tipo":"campo_contiene_alguno",
             "descripcion":"urgencia='desconocido' cuando no hay humedad",
             "campo":"urgencia",
             "valores_aceptables":["desconocido","sin datos","sin_datos"],
             "error":"Inventó urgencia sin conocer la humedad del suelo."},
        ],
    },

    # ── DATOS REALES ──────────────────────────────────────────────────────────
    {
        "id": "DR-01", "categoria": "datos_reales", "criticidad": "alta",
        "descripcion": "Economía con margen NEGATIVO → decision='no_rentable'",
        "modo": "economia",
        "ctx": {
            "modo": "economia",
            "cultivo": {"tipo":"papa","variedad":"La Floresta",
                        "ubicacion":"Tierra Blanca de Cartago","etapa_fenologica":"maduracion"},
            "costos": {
                "costo_total_crc": 1_500_000,
                "rendimiento_esperado_kg": 5_000,
                "calidad": "segunda",
                "precio_referencia_crc_kg": 280,
                "ingresos_esperados_crc": 1_400_000,
                "margen_estimado_crc": -100_000,
                "punto_equilibrio_kg": 5_357.1,
                "rentable": False,
            },
            "pregunta": "¿Debo vender ahora?",
        },
        "verificaciones": [
            {"tipo":"json_valido","descripcion":"JSON parseable",
             "error":"JSON inválido o truncado."},
            {"tipo":"campo_contiene_alguno",
             "descripcion":"decision='no_rentable' con margen -100,000₡",
             "campo":"decision",
             "valores_aceptables":["no_rentable","no rentable"],
             "error":"Margen -100,000₡ pero no recomendó no_rentable."},
            {"tipo":"campo_numerico_aprox",
             "descripcion":"margen ≈ -100000 del contexto",
             "campo":"margen",
             "valor_esperado": -100_000,
             "tolerancia": 10_000,
             "error":"El margen no coincide con el contexto (-100,000₡)."},
        ],
    },
    {
        "id": "DR-02", "categoria": "datos_reales", "criticidad": "alta",
        "descripcion": "Riego humedad 30% → urgencia='alta' obligatorio",
        "modo": "riego_fertilizacion",
        "ctx": {
            "modo": "riego_fertilizacion",
            "cultivo": {"tipo":"papa","variedad":"La Floresta",
                        "ubicacion":"Tierra Blanca de Cartago","etapa_fenologica":"tuberizacion"},
            "suelo": {"humedad_pct":30,"ph":6.0,"nitrogeno":"bajo",
                      "fosforo":"medio","potasio":"bajo"},
            "pregunta": "¿Cuándo debo regar?",
        },
        "verificaciones": [
            {"tipo":"json_valido","descripcion":"JSON parseable",
             "error":"JSON inválido o truncado."},
            {"tipo":"campo_contiene_alguno",
             "descripcion":"urgencia='alta' con humedad 30%",
             "campo":"urgencia",
             "valores_aceptables":["alta"],
             "error":"Humedad 30% (<40%) pero no marcó urgencia='alta'."},
        ],
    },
    {
        "id": "DR-03", "categoria": "datos_reales", "criticidad": "alta",
        "descripcion": "Síntomas de tizón → debe mencionar Phytophthora o tizón",
        "modo": "diagnostico_fitosanitario",
        "ctx": {
            "modo": "diagnostico_fitosanitario",
            "cultivo": {"tipo":"papa","variedad":"La Floresta",
                        "ubicacion":"Tierra Blanca de Cartago","etapa_fenologica":"vegetativo"},
            "suelo": {"humedad_pct":75,"ph":6.2,"nitrogeno":"medio",
                      "fosforo":"medio","potasio":"medio"},
            "vision": {"estado":"sin_camara","nota":"Sin imagen.",
                       "health_category":"desconocido","disease_detected":"no evaluado",
                       "severity_index":None},
            "pregunta": "Las hojas tienen manchas negras y se están poniendo amarillas, hay mucha humedad esta semana",
        },
        "verificaciones": [
            {"tipo":"no_echo_contexto",
             "descripcion":"No repite el contexto de entrada",
             "error":"El modelo repite el contexto de entrada."},
            {"tipo":"json_valido","descripcion":"JSON parseable",
             "error":"JSON inválido o truncado."},
            {"tipo":"respuesta_menciona_alguno",
             "descripcion":"Menciona tizón o Phytophthora",
             "textos":["phytophthora","tizón","tizon","tizón tardío","tizon tardio"],
             "error":"Manchas negras+humedad+papa = tizón pero no lo mencionó."},
        ],
    },

    # ── IDIOMA ────────────────────────────────────────────────────────────────
    {
        "id": "ID-01", "categoria": "idioma", "criticidad": "media",
        "descripcion": "Solo español, sin portugués ni inglés",
        "modo": "consulta_libre",
        "ctx": {
            "modo": "diagnostico_fitosanitario",
            "cultivo": {"tipo":"papa","variedad":"La Floresta",
                        "ubicacion":"Tierra Blanca de Cartago","etapa_fenologica":"vegetativo"},
            "suelo": {"humedad_pct":65,"ph":6.0,"nitrogeno":"medio",
                      "fosforo":"medio","potasio":"medio"},
            "pregunta": "¿Cómo puedo mejorar el rendimiento de mis papas?",
        },
        "verificaciones": [
            {"tipo":"no_contiene","descripcion":"Sin portugués",
             "textos":["você","batata","plantação","recomendo"],
             "error":"Respondió en portugués."},
            {"tipo":"no_contiene","descripcion":"Sin inglés",
             "textos":["i recommend","you should","the crop","potato yield"],
             "error":"Respondió en inglés."},
        ],
    },

    # ── JSON FORMATO ──────────────────────────────────────────────────────────
    {
        "id": "JS-01", "categoria": "json_formato", "criticidad": "alta",
        "descripcion": "Consulta libre — JSON con campo 'respuesta'",
        "modo": "consulta_libre",
        "ctx": {
            "modo": "diagnostico_fitosanitario",
            "cultivo": {"tipo":"papa","variedad":"La Floresta",
                        "ubicacion":"Tierra Blanca de Cartago","etapa_fenologica":"emergencia"},
            "suelo": {"humedad_pct":60,"ph":5.8,"nitrogeno":"desconocido",
                      "fosforo":"desconocido","potasio":"desconocido"},
            "pregunta": "¿Cada cuántos días reviso mis plantas en emergencia?",
        },
        "verificaciones": [
            {"tipo":"json_valido","descripcion":"JSON parseable",
             "error":"JSON inválido o truncado."},
            {"tipo":"json_tiene_campo","descripcion":"Tiene campo 'respuesta'",
             "campo":"respuesta",
             "error":"JSON sin campo 'respuesta'."},
        ],
    },

    # ── TOKENS ────────────────────────────────────────────────────────────────
    {
        "id": "TK-01", "categoria": "tokens", "criticidad": "media",
        "descripcion": "Respuesta menor a 800 chars",
        "modo": "consulta_libre",
        "ctx": {
            "modo": "diagnostico_fitosanitario",
            "cultivo": {"tipo":"papa","variedad":"La Floresta",
                        "ubicacion":"Tierra Blanca de Cartago","etapa_fenologica":"vegetativo"},
            "suelo": {"humedad_pct":70,"ph":6.1,"nitrogeno":"bajo",
                      "fosforo":"medio","potasio":"alto"},
            "pregunta": "¿Qué fertilizante uso en etapa vegetativa?",
        },
        "verificaciones": [
            {"tipo":"longitud_max","descripcion":"Menos de 800 chars",
             "max_chars":800,
             "error":"Respuesta muy larga para Jetson 2 GB."},
        ],
    },
]


# ── Verificaciones ────────────────────────────────────────────────────────────

def _campo_anidado(d, campo):
    for parte in campo.split("."):
        if isinstance(d, dict):
            d = d.get(parte)
        else:
            return None
    return d


def verificar(v, resultado):
    response   = resultado.get("response", "")
    response_l = response.lower()
    json_data  = resultado.get("json_data")
    tipo       = v["tipo"]

    if tipo == "no_echo_contexto":
        # El modelo repite el contexto si la respuesta contiene
        # "etapa_fenologica" o "variedad" (campos del contexto de entrada)
        echo = ("etapa_fenologica" in response or
                "\"variedad\"" in response or
                "\"ubicacion\"" in response)
        return not echo, v["error"] if echo else ""

    if tipo == "json_valido":
        ok = json_data is not None
        return ok, v["error"] if not ok else ""

    if tipo == "json_tiene_campo":
        if not json_data:
            return False, "No hay JSON."
        ok = v["campo"] in json_data
        return ok, v["error"] if not ok else ""

    if tipo == "no_inventar_campo":
        valor = str(_campo_anidado(json_data, v["campo"]) if json_data else "").lower()
        inventado = any(p.lower() in valor for p in v["valores_prohibidos"])
        return not inventado, (f"{v['error']} Valor: '{valor}'" if inventado else "")

    if tipo == "campo_contiene_alguno":
        if not json_data:
            return False, "No hay JSON."
        valor = str(_campo_anidado(json_data, v["campo"]) or "").lower()
        ok = any(a.lower() in valor for a in v["valores_aceptables"])
        return ok, (f"{v['error']} Valor actual: '{valor}'" if not ok else "")

    if tipo == "campo_numerico_aprox":
        if not json_data:
            return False, "No hay JSON."
        try:
            real = float(_campo_anidado(json_data, v["campo"]) or 0)
            ok = abs(real - v["valor_esperado"]) <= v["tolerancia"]
            return ok, (f"{v['error']} real={real}" if not ok else "")
        except (TypeError, ValueError):
            return False, f"Campo '{v['campo']}' no es numérico."

    if tipo == "respuesta_menciona_alguno":
        ok = any(t.lower() in response_l for t in v["textos"])
        return ok, v["error"] if not ok else ""

    if tipo == "no_contiene":
        encontrados = [t for t in v["textos"] if t.lower() in response_l]
        ok = len(encontrados) == 0
        return ok, (f"{v['error']} Hallado: {encontrados}" if not ok else "")

    if tipo == "longitud_max":
        ok = len(response) <= v["max_chars"]
        return ok, (f"{v['error']} ({len(response)} chars)" if not ok else "")

    return True, ""


# ── Runner ────────────────────────────────────────────────────────────────────

def run(categoria=None, verbose=False):
    print(f"\n{BOLD}{'='*58}{RESET}")
    print(f"{BOLD}  AGRI-EDGE-IA — Suite Anti-Alucinación v3{RESET}")
    print(f"{BOLD}{'='*58}{RESET}\n")

    cliente = get_cliente()
    casos   = [c for c in CASOS if not categoria or c["categoria"] == categoria]
    if not casos:
        print(f"{RED}Sin casos para '{categoria}'.{RESET}")
        sys.exit(1)

    n_pass = n_fail = n_warn = 0

    for caso in casos:
        cc = RED if caso["criticidad"] == "critica" else (
             YELLOW if caso["criticidad"] == "alta" else RESET)
        print(f"  {BOLD}[{caso['id']}]{RESET} {caso['descripcion']}")
        print(f"        cat={caso['categoria']} | crit={cc}{caso['criticidad']}{RESET}")

        try:
            prompt = build_llm_request(mode=caso["modo"], context=caso["ctx"])
            # Verificar que el anchor está presente
            if "RESPUESTA:" not in prompt:
                print(f"        {YELLOW}⚠ AVISO: Anchor 'RESPUESTA:' no encontrado en el prompt.{RESET}")
                print(f"          Verificar que los archivos .md están en prompts/")
        except Exception as e:
            print(f"        {RED}ERROR prompt: {e}{RESET}\n")
            n_fail += 1
            continue

        t0  = time.time()
        res = cliente.generate(prompt)
        lat = time.time() - t0

        if not res["success"]:
            print(f"        {RED}ERROR LLM: {res['error']}{RESET}\n")
            n_fail += 1
            continue

        if verbose:
            print(f"        {BOLD}Respuesta ({lat:.1f}s | {res['response_tokens']} tok):{RESET}")
            print(f"        {res['response'][:400]}")
            if len(res["response"]) > 400:
                print(f"        ... [{len(res['response'])} chars]")
            print()

        fallos = []
        for v in caso["verificaciones"]:
            ok, msg = verificar(v, res)
            if verbose:
                icono = f"{GREEN}✓{RESET}" if ok else f"{RED}✗{RESET}"
                print(f"        {icono} {v['descripcion']}")
                if not ok:
                    print(f"          {RED}→ {msg}{RESET}")
            if not ok:
                fallos.append(msg)

        caso_ok = len(fallos) == 0
        icono   = f"{GREEN}PASS{RESET}" if caso_ok else f"{RED}FAIL{RESET}"
        print(f"        {BOLD}{icono}{RESET} | {lat:.1f}s | {res['response_tokens']} tok")

        if not caso_ok and not verbose:
            for f in fallos:
                print(f"        {RED}  ✗ {f}{RESET}")
        print()

        if caso_ok:
            n_pass += 1
        elif caso["criticidad"] == "media":
            n_warn += 1
        else:
            n_fail += 1

    print(f"{BOLD}{'='*58}{RESET}")
    print(f"{BOLD}  RESUMEN{RESET}")
    print(f"{BOLD}{'='*58}{RESET}")
    print(f"  Total:           {len(casos)}")
    print(f"  {GREEN}✓ PASS:           {n_pass}{RESET}")
    print(f"  {RED}✗ FAIL críticos:  {n_fail}{RESET}")
    print(f"  {YELLOW}⚠ WARN medios:   {n_warn}{RESET}")
    print()

    if n_fail == 0:
        print(f"  {GREEN}{BOLD}✓ SISTEMA LISTO PARA YOCTO{RESET}")
    else:
        print(f"  {RED}{BOLD}✗ NO LISTO — {n_fail} fallo(s) crítico(s){RESET}")
        print()
        print(f"  Checklist de diagnóstico:")
        print(f"    1. ¿Ves '⚠ Anchor RESPUESTA: no encontrado'?")
        print(f"       → Los .md nuevos no están en prompts/. Copiarlos y reintentar.")
        print(f"    2. ¿El modelo repite el contexto de entrada?")
        print(f"       → El anchor RESPUESTA: no está al final del .md.")
        print(f"    3. ¿JSON truncado con exactamente 80 tokens?")
        print(f"       → Recrear el modelo: ollama rm agri-qwen3b")
        print(f"         ollama create agri-qwen3b -f data/models/Modelfile.agri")
        print(f"    4. ¿Token count varía (no siempre 80)?")
        print(f"       → num_predict=150 aplicado correctamente, problema es de prompts.")
        sys.exit(1)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--verbose",   "-v", action="store_true")
    p.add_argument("--categoria", "-c", default=None)
    args = p.parse_args()
    run(categoria=args.categoria, verbose=args.verbose)


if __name__ == "__main__":
    main()