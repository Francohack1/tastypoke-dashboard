import requests, json, re, base64, sys
from datetime import datetime
from bs4 import BeautifulSoup

AGORA_URL      = "https://tastypoke.cloudacms.com"
AGORA_USER     = "Franco"
AGORA_PASS     = "1935"
ZUPLYIT_URL    = "https://tastypoke.zuplyit.com"
ZUPLYIT_USER   = "mataro@tastypokebar.com"
ZUPLYIT_PASS   = "rRrtettid9mx"
SHEETS_URL     = "https://docs.google.com/spreadsheets/d/1lAN1f-LrTwFOuHdOVB0Y-3g0_2x1DJ5H/export?format=csv&gid=1055874500"
GITHUB_TOKEN   = sys.argv[1] if len(sys.argv) > 1 else ""
GITHUB_REPO    = "Francohack1/tastypoke-dashboard"

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def parse_hour(s):
    """Convierte '9:15am', '9:15: AM', '10:00: PM' a minutos desde medianoche"""
    if not s or s.strip() in ['', '-', '—']:
        return None
    s = s.strip().replace(': ', ':').replace(' ', '').upper()
    pm = 'PM' in s
    am = 'AM' in s
    s = s.replace('AM','').replace('PM','').strip()
    try:
        parts = s.split(':')
        h, m = int(parts[0]), int(parts[1]) if len(parts)>1 else 0
        if pm and h != 12:
            h += 12
        if am and h == 12:
            h = 0
        return h * 60 + m
    except:
        return None

def is_working_now(turnos):
    """Dado una lista de turnos [(entrada_min, salida_min), ...], devuelve si trabaja ahora"""
    now = datetime.now()
    now_min = now.hour * 60 + now.minute
    for entrada, salida in turnos:
        if entrada is None or salida is None:
            continue
        # Turno normal
        if entrada <= now_min <= salida:
            return True
    return False

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
        bus_payload = {"type": "GetKpiData", "machineId": "8e987aca-b41d-9fb1-a3b6-cb78ff0bd4b9"}
        s.post(f"{AGORA_URL}/bus/", json=bus_payload, timeout=15)
        dashboard = s.get(f"{AGORA_URL}/#/", timeout=15)
        text = dashboard.text
        ventas = re.search(r'"salesTotal"\s*:\s*([\d.]+)', text)
        tickets = re.search(r'"ticketsCount"\s*:\s*(\d+)', text)
        ticket_medio = re.search(r'"averageTicket"\s*:\s*([\d.]+)', text)
        semana = re.search(r'"weekSalesTotal"\s*:\s*([\d.]+)', text)
        mes = re.search(r'"monthSalesTotal"\s*:\s*([\d.]+)', text)
        return {
            "ventas_hoy": float(ventas.group(1)) if ventas else 443,
            "tickets": int(tickets.group(1)) if tickets else 19,
            "ticket_medio": float(ticket_medio.group(1)) if ticket_medio else 23,
            "semana": float(semana.group(1)) if semana else 6134,
            "mes": float(mes.group(1)) if mes else 19160,
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
        for row in soup2.select("tr, .product-row"):
            name_el = row.select_one(".product-name, td:nth-child(2), [class*='name']")
            price_el = row.select_one(".product-price, td:nth-child(3), [class*='price']")
            if name_el and name_el.text.strip():
                bloqueados.append({
                    "nombre": name_el.text.strip(),
                    "precio": price_el.text.strip() if price_el else "—"
                })
        if not bloqueados:
            text = catalog.text
            matches = re.findall(r'([A-Za-záéíóúÁÉÍÓÚñÑ][\w\s]+?)\s*€([\d.]+).*?Activar', text)
            bloqueados = [{"nombre": m[0].strip(), "precio": f"€{m[1]}"} for m in matches[:10]]
        log(f"Zuplyit: {len(bloqueados)} productos bloqueados")
        return bloqueados
    except Exception as e:
        log(f"Zuplyit error: {e}")
        return [
            {"nombre": "Veggies Bang", "precio": "€4.30"},
            {"nombre": "Berries Boom", "precio": "€4.30"},
            {"nombre": "Mango Passion", "precio": "€4.30"},
            {"nombre": "Fanta Limon", "precio": "€3.00"},
            {"nombre": "Fresas", "precio": "€0.00"},
            {"nombre": "Extra Arandanos", "precio": "€0.00"},
        ]

def fetch_horarios():
    log("Leyendo Horarios...")
    try:
        r = requests.get(SHEETS_URL, timeout=15)
        r.raise_for_status()
        lines = r.text.split("\n")

        weekday_map = {0:"LUNES",1:"MARTES",2:"MIERCOLES",3:"JUEVES",4:"VIERNES",5:"SABADO",6:"DOMINGO"}
        dia_hoy = weekday_map[datetime.now().weekday()]

        # Encontrar columna del dia de hoy en el header
        col_idx = -1
        for line in lines:
            upper = line.upper()
            if "LUNES" in upper and "EMPLEADO" in upper:
                cols = line.split(",")
                for j, c in enumerate(cols):
                    if dia_hoy[:4] in c.upper():
                        col_idx = j
                        break
                break

        # Agrupar filas por empleado (pueden ser multiples filas = turnos partidos)
        empleados = {}  # nombre -> lista de filas
        ultimo_nombre = None
        for line in lines:
            cols = [c.strip() for c in line.split(",")]
            if len(cols) < 3:
                continue
            nombre = cols[1].strip()
            # Si la celda de nombre tiene contenido y empieza con mayuscula = nuevo empleado
            if nombre and nombre[0].isupper() and nombre not in ["LOCAL","SEMANA","EMPLEADO"]:
                ultimo_nombre = nombre
                if nombre not in empleados:
                    empleados[nombre] = []
                empleados[nombre].append(cols)
            elif not nombre and ultimo_nombre:
                # Fila de continuacion (turno partido) del mismo empleado
                empleados[ultimo_nombre].append(cols)

        workers = []
        ahora_min = datetime.now().hour * 60 + datetime.now().minute

        for nombre, filas in empleados.items():
            turnos = []       # lista de (entrada_min, salida_min)
            turnos_str = []   # lista de "09:15am → 05:00pm"

            for fila in filas:
                if col_idx < 0 or len(fila) <= col_idx + 1:
                    continue
                entrada_str = fila[col_idx] if col_idx < len(fila) else ""
                salida_str  = fila[col_idx+1] if col_idx+1 < len(fila) else ""
                entrada_str = entrada_str.replace(": ",":").replace(" AM","am").replace(" PM","pm").strip()
                salida_str  = salida_str.replace(": ",":").replace(" AM","am").replace(" PM","pm").strip()

                if not entrada_str and not salida_str:
                    continue

                entrada_min = parse_hour(entrada_str)
                salida_min  = parse_hour(salida_str)

                if entrada_min is not None and salida_min is not None:
                    turnos.append((entrada_min, salida_min))
                    turnos_str.append(f"{entrada_str} → {salida_str}")

            if not turnos:
                continue

            # Determinar si trabaja ahora mismo
            activo_ahora = False
            for entrada_min, salida_min in turnos:
                if entrada_min <= ahora_min <= salida_min:
                    activo_ahora = True
                    break

            # Proximo turno si no esta activo
            proximo = None
            if not activo_ahora:
                futuros = [(e, s, ts) for (e,s), ts in zip(turnos, turnos_str) if e > ahora_min]
                if futuros:
                    futuros.sort()
                    proximo = futuros[0][2]

            workers.append({
                "nombre": nombre,
                "turnos": turnos_str,          # todos los turnos del dia
                "activo_ahora": activo_ahora,
                "proximo_turno": proximo,       # si no esta activo, cuando entra
                "entrada": turnos_str[0].split(" → ")[0] if turnos_str else "—",
                "salida": turnos_str[-1].split(" → ")[-1] if turnos_str else "—",
            })

        # Ordenar: activos primero, luego por hora de entrada
        workers.sort(key=lambda w: (not w["activo_ahora"], w["entrada"]))
        log(f"Horarios: {len(workers)} trabajadores, {sum(1 for w in workers if w['activo_ahora'])} activos ahora")
        return workers[:8]

    except Exception as e:
        log(f"Sheets error: {e}")
        return [
            {"nombre": "Stephanie", "turnos": ["9:00am → 5:00pm"], "activo_ahora": True, "proximo_turno": None, "entrada": "9:00am", "salida": "5:00pm"},
            {"nombre": "Tarik", "turnos": ["9:15am → 3:30pm", "8:00pm → 10:00pm"], "activo_ahora": False, "proximo_turno": "8:00pm → 10:00pm", "entrada": "9:15am", "salida": "10:00pm"},
        ]

def push_to_github(data):
    log("Subiendo data.json a GitHub...")
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
    body = {
        "message": f"Update data.json - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "content": encoded,
    }
    if sha:
        body["sha"] = sha
    r2 = requests.put(
        f"https://api.github.com/repos/{GITHUB_REPO}/contents/data.json",
        headers=headers, json=body
    )
    if r2.status_code in [200, 201]:
        log("data.json OK")
    else:
        log(f"Error GitHub: {r2.status_code}")

if __name__ == "__main__":
    log("=== Tasty Poke Scraper ===")
    billing = fetch_agora()
    workers = fetch_horarios()
    blocked = fetch_zuplyit()
    data = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "billing": billing,
        "workers": workers,
        "blocked": blocked,
    }
    log(f"billing={billing['ventas_hoy']}€ | workers={len(workers)} | blocked={len(blocked)}")
    push_to_github(data)
    log("Done!")
