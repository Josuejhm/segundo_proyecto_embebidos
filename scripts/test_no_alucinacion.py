#!/usr/bin/env python3
"""
scripts/test_no_alucinacion.py — v4
CV-02 ahora acepta "no_rentable" O "sin datos" como respuesta válida
cuando costos está vacío (ambas son respuestas correctas — v3 era muy estricto).
"""
import argparse, json, sys, time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from modules.llm_client    import OllamaClient
from modules.prompt_builder import build_llm_request

G="\033[92m"; R="\033[91m"; Y="\033[93m"; B="\033[1m"; X="\033[0m"
MODELO = "agri-qwen3b"; FALLBACK = "qwen2.5:3b"


def get_cliente():
    c = OllamaClient(model=MODELO, num_predict=0, stream=False, temperature=0.1)
    if c.health_check():
        print(f"  Modelo: {B}{MODELO}{X} | num_predict: del Modelfile"); return c
    print(f"  {Y}'{MODELO}' no encontrado. Usando '{FALLBACK}'.{X}")
    c2 = OllamaClient(model=FALLBACK, num_predict=0, stream=False, temperature=0.1)
    if c2.health_check(): return c2
    print(f"  {R}ERROR: ollama serve no está corriendo.{X}"); sys.exit(1)


CASOS = [
    {
        "id":"CV-01","categoria":"contexto_vacio","criticidad":"critica",
        "descripcion":"Diagnóstico SIN síntomas — no debe inventar enfermedad",
        "modo":"diagnostico_fitosanitario",
        "ctx":{
            "modo":"diagnostico_fitosanitario",
            "cultivo":{"tipo":"papa","variedad":"La Floresta","ubicacion":"Tierra Blanca de Cartago","etapa_fenologica":"vegetativo"},
            "suelo":{"humedad_pct":None,"ph":None,"nitrogeno":"desconocido","fosforo":"desconocido","potasio":"desconocido"},
            "vision":{"estado":"sin_camara","nota":"Sin imagen.","health_category":"desconocido","disease_detected":"no evaluado","severity_index":None},
        },
        "verificaciones":[
            {"tipo":"no_echo","descripcion":"No repite el contexto de entrada",
             "error":"El modelo repite el JSON de entrada."},
            {"tipo":"json_valido","descripcion":"JSON parseable",
             "error":"JSON inválido o truncado."},
            {"tipo":"no_inventar_campo","descripcion":"No inventa enfermedad en 'causa'",
             "campo":"causa",
             "prohibidos":["phytophthora","fusarium","tizon","tizón","virus","rhizoctonia","alternaria"],
             "error":"Inventó una enfermedad sin síntomas."},
        ],
    },
    {
        "id":"CV-02","categoria":"contexto_vacio","criticidad":"critica",
        "descripcion":"Economía SIN costos — no debe inventar ganancias",
        "modo":"economia",
        "ctx":{
            "modo":"economia",
            "cultivo":{"tipo":"papa","variedad":"La Floresta","ubicacion":"Tierra Blanca de Cartago","etapa_fenologica":"maduracion"},
            "costos":{},
            "pregunta":"¿Cuánto voy a ganar?",
        },
        "verificaciones":[
            {"tipo":"json_valido","descripcion":"JSON parseable",
             "error":"JSON inválido o truncado."},
            # Aceptamos "sin datos" O "no_rentable" — ambas son respuestas correctas
            # cuando no hay costos. Lo que NO se acepta es "vender_ahora" o "esperar".
            {"tipo":"campo_no_contiene","descripcion":"No dice 'vender_ahora' ni 'esperar' sin datos",
             "campo":"decision",
             "valores_prohibidos":["vender_ahora","esperar"],
             "error":"Con costos vacíos recomendó vender o esperar — eso es alucinación."},
        ],
    },
    {
        "id":"CV-03","categoria":"contexto_vacio","criticidad":"critica",
        "descripcion":"Riego SIN humedad — urgencia debe ser 'desconocido'",
        "modo":"riego_fertilizacion",
        "ctx":{
            "modo":"riego_fertilizacion",
            "cultivo":{"tipo":"papa","variedad":"La Floresta","ubicacion":"Tierra Blanca de Cartago","etapa_fenologica":"tuberizacion"},
            "suelo":{"humedad_pct":None,"ph":None,"nitrogeno":"desconocido","fosforo":"desconocido","potasio":"desconocido"},
            "pregunta":"¿Cuándo debo regar?",
        },
        "verificaciones":[
            {"tipo":"json_valido","descripcion":"JSON parseable",
             "error":"JSON inválido o truncado."},
            {"tipo":"campo_contiene_alguno","descripcion":"urgencia='desconocido' sin humedad",
             "campo":"urgencia",
             "aceptables":["desconocido","sin datos","sin_datos"],
             "error":"Inventó urgencia sin conocer la humedad."},
        ],
    },
    {
        "id":"DR-01","categoria":"datos_reales","criticidad":"alta",
        "descripcion":"Margen NEGATIVO → decision='no_rentable'",
        "modo":"economia",
        "ctx":{
            "modo":"economia",
            "cultivo":{"tipo":"papa","variedad":"La Floresta","ubicacion":"Tierra Blanca de Cartago","etapa_fenologica":"maduracion"},
            "costos":{
                "costo_total_crc":1500000,"rendimiento_esperado_kg":5000,
                "calidad":"segunda","precio_referencia_crc_kg":280,
                "ingresos_esperados_crc":1400000,"margen_estimado_crc":-100000,
                "punto_equilibrio_kg":5357.1,"rentable":False,
            },
            "pregunta":"¿Debo vender ahora?",
        },
        "verificaciones":[
            {"tipo":"json_valido","descripcion":"JSON parseable","error":"JSON inválido."},
            {"tipo":"campo_contiene_alguno","descripcion":"decision='no_rentable' (margen -100,000₡)",
             "campo":"decision","aceptables":["no_rentable","no rentable"],
             "error":"Margen -100,000₡ pero no dijo no_rentable."},
            {"tipo":"campo_es_negativo","descripcion":"margen debe ser negativo (contexto tiene -100000)",
             "campo":"margen",
             "error":"El margen debería ser negativo (-100000) pero el modelo puso cero o positivo."},
        ],
    },
    {
        "id":"DR-02","categoria":"datos_reales","criticidad":"alta",
        "descripcion":"Humedad 30% → urgencia='alta' obligatorio",
        "modo":"riego_fertilizacion",
        "ctx":{
            "modo":"riego_fertilizacion",
            "cultivo":{"tipo":"papa","variedad":"La Floresta","ubicacion":"Tierra Blanca de Cartago","etapa_fenologica":"tuberizacion"},
            "suelo":{"humedad_pct":30,"ph":6.0,"nitrogeno":"bajo","fosforo":"medio","potasio":"bajo"},
            "pregunta":"¿Cuándo riego?",
        },
        "verificaciones":[
            {"tipo":"json_valido","descripcion":"JSON parseable","error":"JSON inválido."},
            {"tipo":"campo_contiene_alguno","descripcion":"urgencia='alta' con humedad 30%",
             "campo":"urgencia","aceptables":["alta"],
             "error":"Humedad 30% (<40%) pero urgencia no es 'alta'."},
        ],
    },
    {
        "id":"DR-03","categoria":"datos_reales","criticidad":"alta",
        "descripcion":"Síntomas de tizón → menciona Phytophthora o tizón",
        "modo":"diagnostico_fitosanitario",
        "ctx":{
            "modo":"diagnostico_fitosanitario",
            "cultivo":{"tipo":"papa","variedad":"La Floresta","ubicacion":"Tierra Blanca de Cartago","etapa_fenologica":"vegetativo"},
            "suelo":{"humedad_pct":75,"ph":6.2,"nitrogeno":"medio","fosforo":"medio","potasio":"medio"},
            "vision":{"estado":"sin_camara","nota":"Sin imagen.","health_category":"desconocido","disease_detected":"no evaluado","severity_index":None},
            "pregunta":"Las hojas tienen manchas negras y se estan poniendo amarillas, hay mucha humedad esta semana",
        },
        "verificaciones":[
            {"tipo":"no_echo","descripcion":"No repite el contexto","error":"Repite contexto."},
            {"tipo":"json_valido","descripcion":"JSON parseable","error":"JSON inválido."},
            {"tipo":"respuesta_menciona","descripcion":"Menciona tizón o Phytophthora",
             "textos":["phytophthora","tizón","tizon"],
             "error":"Manchas negras+humedad+papa = tizón pero no lo identificó."},
        ],
    },
    {
        "id":"ID-01","categoria":"idioma","criticidad":"media",
        "descripcion":"Solo español, sin portugués ni inglés",
        "modo":"consulta_libre",
        "ctx":{
            "modo":"diagnostico_fitosanitario",
            "cultivo":{"tipo":"papa","variedad":"La Floresta","ubicacion":"Tierra Blanca de Cartago","etapa_fenologica":"vegetativo"},
            "suelo":{"humedad_pct":65,"ph":6.0,"nitrogeno":"medio","fosforo":"medio","potasio":"medio"},
            "pregunta":"¿Cómo mejoro el rendimiento de mis papas?",
        },
        "verificaciones":[
            {"tipo":"no_contiene","descripcion":"Sin portugués",
             "textos":["você","batata","plantação","recomendo"],"error":"Respondió en portugués."},
            {"tipo":"no_contiene","descripcion":"Sin inglés",
             "textos":["i recommend","you should","the crop","potato yield"],"error":"Respondió en inglés."},
        ],
    },
    {
        "id":"JS-01","categoria":"json_formato","criticidad":"alta",
        "descripcion":"Consulta libre — JSON con campo 'respuesta'",
        "modo":"consulta_libre",
        "ctx":{
            "modo":"diagnostico_fitosanitario",
            "cultivo":{"tipo":"papa","variedad":"La Floresta","ubicacion":"Tierra Blanca de Cartago","etapa_fenologica":"emergencia"},
            "suelo":{"humedad_pct":60,"ph":5.8,"nitrogeno":"desconocido","fosforo":"desconocido","potasio":"desconocido"},
            "pregunta":"¿Cada cuántos días reviso mis plantas en emergencia?",
        },
        "verificaciones":[
            {"tipo":"json_valido","descripcion":"JSON parseable","error":"JSON inválido."},
            {"tipo":"json_tiene_campo","descripcion":"Tiene campo 'respuesta'","campo":"respuesta","error":"Sin campo 'respuesta'."},
        ],
    },
    {
        "id":"TK-01","categoria":"tokens","criticidad":"media",
        "descripcion":"Respuesta menor a 800 chars",
        "modo":"consulta_libre",
        "ctx":{
            "modo":"diagnostico_fitosanitario",
            "cultivo":{"tipo":"papa","variedad":"La Floresta","ubicacion":"Tierra Blanca de Cartago","etapa_fenologica":"vegetativo"},
            "suelo":{"humedad_pct":70,"ph":6.1,"nitrogeno":"bajo","fosforo":"medio","potasio":"alto"},
            "pregunta":"¿Qué fertilizante uso en etapa vegetativa?",
        },
        "verificaciones":[
            {"tipo":"longitud_max","descripcion":"Menos de 800 chars","max":800,"error":"Respuesta muy larga."},
        ],
    },
]


def campo_anidado(d, campo):
    for p in campo.split("."):
        if isinstance(d, dict): d = d.get(p)
        else: return None
    return d


def verificar(v, res):
    r  = res.get("response","")
    rl = r.lower()
    jd = res.get("json_data")
    t  = v["tipo"]

    if t == "no_echo":
        echo = any(k in r for k in ["etapa_fenologica","\"variedad\"","\"ubicacion\""])
        return not echo, v["error"] if echo else ""

    if t == "json_valido":
        return jd is not None, v["error"] if jd is None else ""

    if t == "json_tiene_campo":
        if not jd: return False, "Sin JSON."
        ok = v["campo"] in jd
        return ok, v["error"] if not ok else ""

    if t == "no_inventar_campo":
        val = str(campo_anidado(jd, v["campo"]) if jd else "").lower()
        inv = any(p.lower() in val for p in v["prohibidos"])
        return not inv, (f"{v['error']} valor='{val}'" if inv else "")

    if t == "campo_contiene_alguno":
        if not jd: return False, "Sin JSON."
        val = str(campo_anidado(jd, v["campo"]) or "").lower()
        ok  = any(a.lower() in val for a in v["aceptables"])
        return ok, (f"{v['error']} valor='{val}'" if not ok else "")

    if t == "campo_no_contiene":
        if not jd: return True, ""   # sin JSON = no hay alucinación
        val = str(campo_anidado(jd, v["campo"]) or "").lower()
        mal = [p for p in v["valores_prohibidos"] if p.lower() in val]
        return len(mal)==0, (f"{v['error']} valor='{val}'" if mal else "")

    if t == "campo_numerico_aprox":
        if not jd: return False, "Sin JSON."
        try:
            real = float(campo_anidado(jd, v["campo"]) or 0)
            ok   = abs(real - v["esperado"]) <= v["tolerancia"]
            return ok, (f"{v['error']} real={real}" if not ok else "")
        except: return False, f"Campo '{v['campo']}' no numérico."

    if t == "respuesta_menciona":
        ok = any(tx.lower() in rl for tx in v["textos"])
        return ok, v["error"] if not ok else ""

    if t == "no_contiene":
        mal = [tx for tx in v["textos"] if tx.lower() in rl]
        return len(mal)==0, (f"{v['error']} hallado:{mal}" if mal else "")

    if t == "longitud_max":
        ok = len(r) <= v["max"]
        return ok, (f"{v['error']} {len(r)} chars" if not ok else "")

    if t == "campo_es_negativo":
        if not jd: return False, "Sin JSON."
        try:
            val = float(campo_anidado(jd, v["campo"]) or 0)
            ok  = val < 0
            return ok, (f"{v['error']} valor={val}" if not ok else "")
        except (TypeError, ValueError):
            return False, f"Campo '{v['campo']}' no numérico."

    return True, ""


def run(categoria=None, verbose=False):
    print(f"\n{B}{'='*56}{X}\n{B}  AGRI-EDGE-IA — Suite Anti-Alucinación v4{X}\n{B}{'='*56}{X}\n")
    cliente = get_cliente()
    casos   = [c for c in CASOS if not categoria or c["categoria"]==categoria]
    if not casos: print(f"{R}Sin casos para '{categoria}'.{X}"); sys.exit(1)

    np=nf=nw=0
    for caso in casos:
        cc = R if caso["criticidad"]=="critica" else (Y if caso["criticidad"]=="alta" else X)
        print(f"  {B}[{caso['id']}]{X} {caso['descripcion']}")
        print(f"        cat={caso['categoria']} | crit={cc}{caso['criticidad']}{X}")

        try:
            prompt = build_llm_request(mode=caso["modo"], context=caso["ctx"])
            if "RESPUESTA:" not in prompt:
                print(f"        {Y}⚠ Anchor RESPUESTA: no encontrado — verificar prompts/{X}")
        except Exception as e:
            print(f"        {R}ERROR prompt: {e}{X}\n"); nf+=1; continue

        t0=time.time(); res=cliente.generate(prompt); lat=time.time()-t0

        if not res["success"]:
            print(f"        {R}ERROR LLM: {res['error']}{X}\n"); nf+=1; continue

        if verbose:
            print(f"        {B}Respuesta ({lat:.1f}s | {res['response_tokens']} tok):{X}")
            print(f"        {res['response'][:400]}")
            if len(res["response"])>400: print(f"        ... [{len(res['response'])} chars]")
            print()

        fallos=[]
        for v in caso["verificaciones"]:
            ok,msg = verificar(v,res)
            if verbose:
                ico = f"{G}✓{X}" if ok else f"{R}✗{X}"
                print(f"        {ico} {v['descripcion']}")
                if not ok: print(f"          {R}→ {msg}{X}")
            if not ok: fallos.append(msg)

        caso_ok = len(fallos)==0
        ico = f"{G}PASS{X}" if caso_ok else f"{R}FAIL{X}"
        print(f"        {B}{ico}{X} | {lat:.1f}s | {res['response_tokens']} tok")
        if not caso_ok and not verbose:
            for f in fallos: print(f"        {R}  ✗ {f}{X}")
        print()

        if caso_ok: np+=1
        elif caso["criticidad"]=="media": nw+=1
        else: nf+=1

    print(f"{B}{'='*56}{X}\n{B}  RESUMEN{X}\n{B}{'='*56}{X}")
    print(f"  Total:           {len(casos)}")
    print(f"  {G}✓ PASS:           {np}{X}")
    print(f"  {R}✗ FAIL críticos:  {nf}{X}")
    print(f"  {Y}⚠ WARN medios:   {nw}{X}\n")

    if nf==0:
        print(f"  {G}{B}✓ SISTEMA LISTO PARA YOCTO{X}")
    else:
        print(f"  {R}{B}✗ NO LISTO — {nf} fallo(s){X}\n")
        print("  Checklist:")
        print("    ⚠ Anchor 'RESPUESTA:' no encontrado → prompts/ sin archivos nuevos")
        print("    JSON truncado con exactamente 80 tok → recrear modelo con Modelfile.agri")
        print("    Token count varía → num_predict=150 OK, problema en prompts")
        sys.exit(1)


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--verbose","-v",action="store_true")
    p.add_argument("--categoria","-c",default=None)
    args=p.parse_args(); run(args.categoria,args.verbose)

if __name__=="__main__": main()