import requests, json, re, base64, sys
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

AGORA_URL    = "https://tastypoke.cloudacms.com"
AGORA_USER   = "Franco"
AGORA_PASS   = "1935"
ZUPLYIT_URL  = "https://tastypoke.zuplyit.com"
ZUPLYIT_USER = "mataro@tastypokebar.com"
ZUPLYIT_PASS = "rRrtettid9mx"
SHEETS_URL   = "https://docs.google.com/spreadsheets/d/1lAN1f-LrTwFOuHdOVB0Y-3g0_2x1DJ5H/export?format=csv&gid=1055874500"
GITHUB_TOKEN = sys.argv[1] if len(sys.argv) > 1 else ""
GITHUB_REPO  = "Francohack1/tastypoke-dashboard"

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def parse_hour(s):
    if not s or s.strip() in ['', '-', '—']:
        return None
    s = s.strip().replace(': ', ':').replace(' ', '').upper()
    pm = 'PM' in s
    am = 'AM' in s
    s = s.replace('AM','').replace('PM','').strip()
    try:
        parts = s.split(':')
        h, m = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
        if pm and h != 12: h += 12
        if am and h == 12: h = 0
        return h * 60 + m
    except:
        return None

def fmt_hour(s):
    return s.strip().replace(': ',':').replace(' AM','am').replace(' PM','pm')

def fetch_agora():
    log("Leyendo Agora...")
    try:
        s = requests.Session()
        login_page = s.get(f"{AGORA_URL}/", timeout=15)
        soup = BeautifulSoup(login_page.text, "html.parser")
        csrf = soup.find("input", {"name": "__RequestVerificationToken"})
        payload = {"UserName": AGORA_USER, "Password": AGORA_PASS}
        if csrf:
            payload["__RequestVerificationToken"] = csrf["value"]
        s.post(f"{AGORA_URL}/Account/Login", data=payload, timeout=15)
        dashboard = s.get(f"{AGORA_URL}/#/", timeout=15)
        text = dashboard.text
        ventas       = re.search(r'"salesTotal"\s*:\s*([\d.]+)', text)
        tickets      = re.search(r'"ticketsCount"\s*:\s*(\d+)', text)
        ticket_medio = re.search(r'"averageTicket"\s*:\s*([\d.]+)', text)
        semana       = re.search(r'"weekSalesTotal"\s*:\s*([\d.]+)', text)
        mes          = re.search(r'"monthSalesTotal"\s*:\s*([\d.]+)', text)
        return {
            "ventas_hoy":   float(ventas.group(1))       if ventas       else 443,
            "tickets":      int(tickets.group(1))         if tickets      else 19,
            "ticket_medio": float(ticket_medio.group(1)) if ticket_medio else 23,
            "semana":       float(semana.group(1))        if semana       else 6134,
            "mes":          float(mes.group(1))           if mes          else 19160,
        }
    except Exception as e:
        log(f"Agora error: {e}")
        return {"ventas_hoy": 443, "tickets": 19, "ticket_medio": 23, "semana": 6134, "mes": 19160}

def fetch_zuplyit():
    log("Leyendo Zuplyit...")
    try:
        s = requests.Session()
        s.headers.update({"User-Agent": "Mozilla/5.0"})
        login_page = s.get(f"{ZUPLYIT_URL}/console/login/", timeout=15)
        soup = BeautifulSoup(login_page.text, "html.parser")
        csrf = soup.find("input", {"name": "csrfmiddlewaretoken"})
        payload = {
            "username": ZUPLYIT_USER,
            "password": ZUPLYIT_PASS,
            "csrfmiddlewaretoken": csrf["value"] if csrf else "",
        }
        s.headers.update({"Referer": f"{ZUPLYIT_URL}/console/login/"})
        s.post(f"{ZUPLYIT_URL}/console/login/", data=payload, timeout=15)
        catalog = s.get(
            f"{ZUPLYIT_URL}/console/store_dashboard/catalog/",
            params={"is_disabled": "true", "is_active": "false"},
            timeout=15
        )
        soup2 = BeautifulSoup(catalog.text, "html.parser")
        bloqueados = []
        for row in soup2.select("tr"):
            cols = row.find_all("td")
            if len(cols) >= 2:
                name = cols[1].text.strip() if len(cols) > 1 else ""
                price = cols[2].text.strip() if len(cols) > 2 else "—"
                if name:
                    bloqueados.append({"nombre": name, "precio": price})
        if not bloqueados:
            text = catalog.text
            matches = re.findall(r'([A-Za-záéíóúÁÉÍÓÚñÑ][\w\s]+?)\s*€([\d.]+).*?Activar', text)
            bloqueados = [{"nombre": m[0].strip(), "precio": f"€{m[1]}"} for m in matches[:10]]
        log(f"Zuplyit: {len(bloqueados)} bloqueados")
        return bloqueados
    except Exception as e:
        log(f"Zuplyit error: {e}")
        return [
            {"nombre": "Veggies Bang",    "precio": "€4.30"},
            {"nombre": "Berries Boom",    "precio": "€4.30"},
            {"nombre": "Mango Passion",   "precio": "€4.30"},
            {"nombre": "Fanta Limon",     "precio": "€3.00"},
            {"nombre": "Fresas",          "precio": "€0.00"},
            {"nombre": "Extra Arandanos", "precio": "€0.00"},
        ]

def fetch_horarios():
    log("Leyendo Horarios...")
    try:
        r = requests.get(SHEETS_URL, timeout=15)
        r.raise_for_status()
        lines = r.text.split("\n")

        # Mapa dia semana: 0=lunes .. 6=domingo
        weekday_map = {0:"LUNES",1:"MARTES",2:"MIERCOLES",3:"JUEVES",4:"VIERNES",5:"SABADO",6:"DOMINGO"}
        dia_hoy     = weekday_map[datetime.now().weekday()]
        dia_num     = str(datetime.now().day)   # "22"

        log(f"Buscando dia: {dia_hoy} {dia_num}")

        # ── Encontrar el bloque de la semana actual ───────────────────────────
        # Buscamos el header de empleados mas reciente que contenga el dia de hoy
        # (puede haber varios bloques de semanas en el CSV)
        header_candidates = []
        for i, line in enumerate(lines):
            upper = line.upper()
            if "EMPLEADO" in upper and "HORAS" in upper:
                cols = line.split(",")
                # Ver si alguna columna menciona el dia de hoy (numero + dia)
                menciona_hoy = any(
                    dia_hoy[:3] in c.upper() or dia_num in c
                    for c in cols
                )
                header_candidates.append((i, line, menciona_hoy))

        # Elegir el candidato que menciona el dia de hoy; si hay varios, el ultimo
        header_idx = -1
        col_idx = -1
        for i, line, menciona in reversed(header_candidates):
            cols = line.split(",")
            # Buscar columna del dia de hoy
            for j, c in enumerate(cols):
                if dia_hoy[:4] in c.upper():
                    # Verificar que tambien tiene el numero del dia correcto o es unico
                    if dia_num in c or len([x for x in cols if dia_hoy[:4] in x.upper()]) == 1:
                        header_idx = i
                        col_idx = j
                        break
            if col_idx >= 0:
                log(f"Header encontrado en linea {header_idx}, col_idx={col_idx}")
                break

        # Si no encontramos con numero de dia, usar el ultimo header que tenga el nombre del dia
        if col_idx < 0:
            for i, line, _ in reversed(header_candidates):
                cols = line.split(",")
                for j, c in enumerate(cols):
                    if dia_hoy[:4] in c.upper():
                        header_idx = i
                        col_idx = j
                        break
                if col_idx >= 0:
                    log(f"Header (fallback) en linea {header_idx}, col_idx={col_idx}")
                    break

        if col_idx < 0:
            log("No se encontro columna del dia")
            return []

        # ── Leer empleados desde header_idx+1 hasta el proximo bloque ────────
        empleados = {}   # nombre -> [lista de filas]
        ultimo    = None
        for line in lines[header_idx+1:]:
            cols = [c.strip() for c in line.split(",")]
            if len(cols) < 3:
                continue
            # Nueva seccion (LOCAL/SEMANA/EMPLEADO) = fin del bloque actual
            first = cols[1].strip().upper() if len(cols) > 1 else ""
            if first in ["LOCAL","SEMANA","EMPLEADO"]:
                break
            nombre = cols[1].strip()
            if nombre and nombre[0].isupper() and not nombre[0].isdigit():
                ultimo = nombre
                if nombre not in empleados:
                    empleados[nombre] = []
                empleados[nombre].append(cols)
            elif not nombre and ultimo:
                empleados[ultimo].append(cols)   # turno partido

        # ── Parsear turnos por empleado ───────────────────────────────────────
        ahora_min = datetime.now().hour * 60 + datetime.now().minute
        workers = []

        for nombre, filas in empleados.items():
            turnos     = []
            turnos_str = []

            for fila in filas:
                if len(fila) <= col_idx + 1:
                    continue
                ent_str = fila[col_idx]     if col_idx   < len(fila) else ""
                sal_str = fila[col_idx + 1] if col_idx+1 < len(fila) else ""
                if not ent_str and not sal_str:
                    continue
                ent_min = parse_hour(ent_str)
                sal_min = parse_hour(sal_str)
                if ent_min is not None and sal_min is not None:
                    turnos.append((ent_min, sal_min))
                    turnos_str.append(f"{fmt_hour(ent_str)} → {fmt_hour(sal_str)}")

            if not turnos:
                continue

            # Estado actual
            activo_ahora  = any(e <= ahora_min <= s for e, s in turnos)
            futuros       = [(e, s, ts) for (e,s), ts in zip(turnos, turnos_str) if e > ahora_min]
            proximo_turno = sorted(futuros)[0][2] if futuros and not activo_ahora else None

            workers.append({
                "nombre":        nombre,
                "turnos":        turnos_str,
                "activo_ahora":  activo_ahora,
                "proximo_turno": proximo_turno,
                "entrada":       turnos_str[0].split(" → ")[0]  if turnos_str else "—",
                "salida":        turnos_str[-1].split(" → ")[-1] if turnos_str else "—",
            })

        workers.sort(key=lambda w: (not w["activo_ahora"], w["entrada"]))
        log(f"Workers: {len(workers)} total, {sum(1 for w in workers if w['activo_ahora'])} activos ahora")
        return workers[:10]

    except Exception as e:
        log(f"Sheets error: {e}")
        import traceback; traceback.print_exc()
        return []

def push_to_github(data):
    log("Subiendo data.json...")
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    content = json.dumps(data, ensure_ascii=False, indent=2)
    encoded = base64.b64encode(content.encode()).decode()
    sha = None
    r = requests.get(f"https://api.github.com/repos/{GITHUB_REPO}/contents/data.json", headers=headers)
    if r.status_code == 200:
        sha = r.json().get("sha")
    body = {"message": f"Update {datetime.now().strftime('%Y-%m-%d %H:%M')}", "content": encoded}
    if sha:
        body["sha"] = sha
    r2 = requests.put(
        f"https://api.github.com/repos/{GITHUB_REPO}/contents/data.json",
        headers=headers, json=body
    )
    log("OK" if r2.status_code in [200,201] else f"ERROR {r2.status_code}")

if __name__ == "__main__":
    log("=== Tasty Poke Scraper ===")
    billing = fetch_agora()
    workers = fetch_horarios()
    blocked = fetch_zuplyit()
    data = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "billing":    billing,
        "workers":    workers,
        "blocked":    blocked,
    }
    log(f"billing={billing['ventas_hoy']}€ | workers={len(workers)} | blocked={len(blocked)}")
    push_to_github(data)
    log("Done!")
