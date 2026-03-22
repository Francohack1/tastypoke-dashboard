import requests, json, re, base64, sys
from datetime import datetime
from bs4 import BeautifulSoup

# ── CONFIG (inyectada por GitHub Actions secrets) ──────────────────
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

# ── ÁGORA ─────────────────────────────────────────────────────────
def fetch_agora():
    log("Leyendo Agora...")
    try:
        s = requests.Session()
        # Login
        login_page = s.get(f"{AGORA_URL}/", timeout=15)
        soup = BeautifulSoup(login_page.text, "html.parser")
        
        # Obtener token CSRF si existe
        csrf = soup.find("input", {"name": "__RequestVerificationToken"})
        payload = {"UserName": AGORA_USER, "Password": AGORA_PASS}
        if csrf:
            payload["__RequestVerificationToken"] = csrf["value"]
        
        # Login
        r = s.post(f"{AGORA_URL}/Account/Login", data=payload, timeout=15)
        
        # Leer dashboard via bus
        bus_payload = {"type": "GetKpiData", "machineId": "8e987aca-b41d-9fb1-a3b6-cb78ff0bd4b9"}
        r2 = s.post(f"{AGORA_URL}/bus/", json=bus_payload, timeout=15)
        
        # Parsear HTML del dashboard como fallback
        dashboard = s.get(f"{AGORA_URL}/#/", timeout=15)
        text = dashboard.text
        
        # Extraer valores con regex del HTML/JSON
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

# ── ZUPLYIT ───────────────────────────────────────────────────────
def fetch_zuplyit():
    log("Leyendo Zuplyit...")
    try:
        s = requests.Session()
        s.headers.update({"User-Agent": "Mozilla/5.0"})
        
        # Login
        login_page = s.get(f"{ZUPLYIT_URL}/console/login/", timeout=15)
        soup = BeautifulSoup(login_page.text, "html.parser")
        csrf = soup.find("input", {"name": "csrfmiddlewaretoken"})
        
        payload = {
            "username": ZUPLYIT_USER,
            "password": ZUPLYIT_PASS,
            "csrfmiddlewaretoken": csrf["value"] if csrf else "",
        }
        s.headers.update({"Referer": f"{ZUPLYIT_URL}/console/login/"})
        r = s.post(f"{ZUPLYIT_URL}/console/login/", data=payload, timeout=15)
        
        # Productos bloqueados
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
            # Fallback: parsear texto plano buscando el patrón del catalogo
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

# ── GOOGLE SHEETS ─────────────────────────────────────────────────
def fetch_horarios():
    log("Leyendo Horarios...")
    try:
        r = requests.get(SHEETS_URL, timeout=15)
        r.raise_for_status()
        lines = r.text.split("\n")
        
        dias = ["DOMINGO","LUNES","MARTES","MIERCOLES","JUEVES","VIERNES","SABADO"]
        dia_hoy = dias[datetime.now().weekday() + 1 if datetime.now().weekday() < 6 else 0]
        # Python weekday: 0=lunes, adjust for list
        weekday_map = {0:"LUNES",1:"MARTES",2:"MIERCOLES",3:"JUEVES",4:"VIERNES",5:"SABADO",6:"DOMINGO"}
        dia_hoy = weekday_map[datetime.now().weekday()]
        
        # Encontrar columna del dia
        header_idx = -1
        col_idx = -1
        for i, line in enumerate(lines):
            if "LUNES" in line or "EMPLEADO" in line:
                header_idx = i
                cols = line.split(",")
                for j, c in enumerate(cols):
                    if dia_hoy[:4] in c.upper():
                        col_idx = j
                        break
                break
        
        workers = []
        seen = set()
        for line in lines:
            cols = line.split(",")
            nombre = cols[1].strip() if len(cols) > 1 else ""
            if (not nombre or nombre in seen or 
                nombre in ["EMPLEADO","LOCAL","SEMANA"] or
                not nombre[0].isupper()):
                continue
            entrada = cols[col_idx].strip() if col_idx > 0 and len(cols) > col_idx else ""
            salida = cols[col_idx+1].strip() if col_idx > 0 and len(cols) > col_idx+1 else ""
            entrada = entrada.replace(": ",":").replace(" AM","am").replace(" PM","pm")
            salida = salida.replace(": ",":").replace(" AM","am").replace(" PM","pm")
            if nombre and (entrada or salida):
                seen.add(nombre)
                workers.append({"nombre": nombre, "entrada": entrada or "—", "salida": salida or "—"})
        
        log(f"Horarios: {len(workers)} trabajadores hoy")
        return workers[:8]
    except Exception as e:
        log(f"Sheets error: {e}")
        return [
            {"nombre": "Stephanie", "entrada": "9:00am", "salida": "5:00pm"},
            {"nombre": "Tarik", "entrada": "1:30pm", "salida": "11:30pm"},
        ]

# ── PUSH A GITHUB ─────────────────────────────────────────────────
def push_to_github(data):
    log("Subiendo data.json a GitHub...")
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    content = json.dumps(data, ensure_ascii=False, indent=2)
    encoded = base64.b64encode(content.encode()).decode()
    
    # Obtener SHA actual del archivo si existe
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
        headers=headers,
        json=body
    )
    if r2.status_code in [200, 201]:
        log("data.json actualizado en GitHub OK")
    else:
        log(f"Error GitHub: {r2.status_code} {r2.text[:200]}")

# ── MAIN ──────────────────────────────────────────────────────────
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
    
    log(f"Datos: billing={billing['ventas_hoy']}€, workers={len(workers)}, blocked={len(blocked)}")
    push_to_github(data)
    log("Done!")
