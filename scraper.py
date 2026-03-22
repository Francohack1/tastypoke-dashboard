import requests, json, re, base64, sys, os
from datetime import datetime
from bs4 import BeautifulSoup

# Credenciales desde GitHub Secrets (variables de entorno)
AGORA_URL    = "https://tastypoke.cloudacms.com"
AGORA_USER   = os.environ["AGORA_USER"]
AGORA_PASS   = os.environ["AGORA_PASS"]
ZUPLYIT_URL  = "https://tastypoke.zuplyit.com"
ZUPLYIT_USER = os.environ["ZUPLYIT_USER"]
ZUPLYIT_PASS = os.environ["ZUPLYIT_PASS"]
SHEETS_URL   = "https://docs.google.com/spreadsheets/d/1lAN1f-LrTwFOuHdOVB0Y-3g0_2x1DJ5H/export?format=csv&gid=1055874500"
GITHUB_TOKEN = os.environ.get("GH_TOKEN", sys.argv[1] if len(sys.argv)>1 else "")
GITHUB_REPO  = "Francohack1/tastypoke-dashboard"

def log(msg): print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def parse_hour(s):
    if not s or not s.strip(): return None
    s = s.strip().replace(': ',':').replace(' ','').upper()
    pm, am = 'PM' in s, 'AM' in s
    s = s.replace('AM','').replace('PM','')
    try:
        parts = s.split(':'); h,m = int(parts[0]), int(parts[1]) if len(parts)>1 else 0
        if pm and h!=12: h+=12
        if am and h==12: h=0
        return h*60+m
    except: return None

def fmt_hour(s): return s.strip().replace(': ',':').replace(' AM','am').replace(' PM','pm')

def fetch_agora():
    log("Leyendo Agora...")
    try:
        s = requests.Session()
        r = s.get(f"{AGORA_URL}/", timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        csrf = soup.find("input", {"name":"__RequestVerificationToken"})
        payload = {"UserName":AGORA_USER,"Password":AGORA_PASS}
        if csrf: payload["__RequestVerificationToken"] = csrf["value"]
        s.post(f"{AGORA_URL}/Account/Login", data=payload, timeout=15)
        dash = s.get(f"{AGORA_URL}/#/", timeout=15)
        t = dash.text
        ventas  = re.search(r'"salesTotal"\s*:\s*([\d.]+)', t)
        tickets = re.search(r'"ticketsCount"\s*:\s*(\d+)', t)
        tmed    = re.search(r'"averageTicket"\s*:\s*([\d.]+)', t)
        semana  = re.search(r'"weekSalesTotal"\s*:\s*([\d.]+)', t)
        mes     = re.search(r'"monthSalesTotal"\s*:\s*([\d.]+)', t)
        result = {
            "ventas_hoy":   float(ventas.group(1))  if ventas  else 0,
            "tickets":      int(tickets.group(1))   if tickets else 0,
            "ticket_medio": float(tmed.group(1))    if tmed    else 0,
            "semana":       float(semana.group(1))  if semana  else 0,
            "mes":          float(mes.group(1))     if mes     else 0,
        }
        log(f"Agora OK: {result['ventas_hoy']}€ hoy")
        return result
    except Exception as e:
        log(f"Agora error: {e}")
        return {"ventas_hoy":0,"tickets":0,"ticket_medio":0,"semana":0,"mes":0}

def fetch_zuplyit():
    log("Leyendo Zuplyit...")
    try:
        s = requests.Session()
        s.headers.update({"User-Agent":"Mozilla/5.0"})
        r = s.get(f"{ZUPLYIT_URL}/console/login/", timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        csrf = soup.find("input", {"name":"csrfmiddlewaretoken"})
        s.headers.update({"Referer":f"{ZUPLYIT_URL}/console/login/"})
        s.post(f"{ZUPLYIT_URL}/console/login/", data={
            "username":ZUPLYIT_USER,"password":ZUPLYIT_PASS,
            "csrfmiddlewaretoken":csrf["value"] if csrf else ""
        }, timeout=15)
        cat = s.get(f"{ZUPLYIT_URL}/console/store_dashboard/catalog/",
                    params={"is_disabled":"true","is_active":"false"}, timeout=15)
        soup2 = BeautifulSoup(cat.text, "html.parser")
        blocked = []
        for tr in soup2.select("tr"):
            tds = tr.find_all("td")
            if len(tds)>=2 and tds[1].text.strip():
                blocked.append({"nombre":tds[1].text.strip(),"precio":tds[2].text.strip() if len(tds)>2 else "—"})
        if not blocked:
            for m in re.findall(r'([A-Za-záéíóúÁÉÍÓÚñÑ][\w\s]+?)\s*€([\d.]+).*?Activar', cat.text):
                blocked.append({"nombre":m[0].strip(),"precio":f"€{m[1]}"})
        log(f"Zuplyit OK: {len(blocked)} bloqueados")
        return blocked
    except Exception as e:
        log(f"Zuplyit error: {e}")
        return []

def fetch_horarios():
    log("Leyendo Horarios...")
    try:
        r = requests.get(SHEETS_URL, timeout=15); r.raise_for_status()
        lines = r.text.split("\n")
        now = datetime.now()
        js_to_es = {0:"LUNES",1:"MARTES",2:"MIERCOLES",3:"JUEVES",4:"VIERNES",5:"SABADO",6:"DOMINGO"}
        dia_es  = js_to_es[now.weekday()]
        dia_num = str(now.day)
        log(f"Buscando {dia_es} {dia_num}")

        # Buscar todos los headers con el dia de hoy + numero
        candidatos = []
        for i, line in enumerate(lines):
            if "EMPLEADO" not in line or "HORAS" not in line: continue
            cols = line.split(",")
            for j, c in enumerate(cols):
                if dia_es[:4] in c.upper() and dia_num in c:
                    n = sum(1 for k in range(i+1,min(i+20,len(lines)))
                            if j<len(lines[k].split(",")) and
                               re.search(r'\d+:\d+', lines[k].split(",")[j]))
                    candidatos.append((i,j,n))

        # Fallback: solo nombre del dia
        if not candidatos:
            for i, line in enumerate(lines):
                if "EMPLEADO" not in line or "HORAS" not in line: continue
                cols = line.split(",")
                for j, c in enumerate(cols):
                    if dia_es[:4] in c.upper():
                        n = sum(1 for k in range(i+1,min(i+20,len(lines)))
                                if j<len(lines[k].split(",")) and
                                   re.search(r'\d+:\d+', lines[k].split(",")[j]))
                        candidatos.append((i,j,n))

        if not candidatos: log("Sin candidatos"); return []

        # Elegir el que tiene mas horas reales
        candidatos.sort(key=lambda x:(x[2]>0, x[2], x[0]), reverse=True)
        header_idx, col_idx, n_horas = candidatos[0]
        log(f"Header linea {header_idx}, col {col_idx}, {n_horas} turnos")

        # Parsear empleados
        empleados, ultimo = {}, None
        for line in lines[header_idx+1:]:
            cols = [c.strip() for c in line.split(",")]
            nom = cols[1] if len(cols)>1 else ""
            if nom.upper() in ["LOCAL","SEMANA","EMPLEADO"]: break
            if nom and nom[0].isupper():
                ultimo = nom
                if nom not in empleados: empleados[nom]=[]
                empleados[nom].append(cols)
            elif not nom and ultimo:
                empleados[ultimo].append(cols)

        ahora = now.hour*60+now.minute
        workers = []
        for nombre, filas in empleados.items():
            turnos, strs = [], []
            for fila in filas:
                if col_idx<0 or len(fila)<=col_idx+1: continue
                ent,sal = fila[col_idx],fila[col_idx+1]
                if not ent and not sal: continue
                em,sm = parse_hour(ent),parse_hour(sal)
                if em is not None and sm is not None:
                    turnos.append((em,sm)); strs.append(f"{fmt_hour(ent)} → {fmt_hour(sal)}")
            if not turnos: continue
            activo = any(e<=ahora<=s for e,s in turnos)
            futuros = sorted([(e,ts) for (e,s),ts in zip(turnos,strs) if e>ahora])
            proximo = futuros[0][1] if futuros and not activo else None
            workers.append({
                "nombre":nombre,"turnos":strs,"activo_ahora":activo,
                "proximo_turno":proximo,
                "entrada":strs[0].split(" → ")[0] if strs else "—",
                "salida":strs[-1].split(" → ")[1] if strs else "—"
            })
        workers.sort(key=lambda w:(not w["activo_ahora"],w["entrada"]))
        log(f"Workers: {len(workers)}, activos: {sum(1 for w in workers if w['activo_ahora'])}")
        return workers[:10]
    except Exception as e:
        log(f"Sheets error: {e}")
        import traceback; traceback.print_exc()
        return []

def push_to_github(data):
    log("Subiendo data.json...")
    hdrs = {"Authorization":f"token {GITHUB_TOKEN}","Accept":"application/vnd.github.v3+json"}
    content = json.dumps(data, ensure_ascii=False, indent=2)
    encoded = base64.b64encode(content.encode()).decode()
    r = requests.get(f"https://api.github.com/repos/{GITHUB_REPO}/contents/data.json", headers=hdrs)
    sha = r.json().get("sha") if r.status_code==200 else None
    body = {"message":f"Auto-update {datetime.now().strftime('%Y-%m-%d %H:%M')}","content":encoded}
    if sha: body["sha"] = sha
    r2 = requests.put(f"https://api.github.com/repos/{GITHUB_REPO}/contents/data.json",headers=hdrs,json=body)
    log("OK ✅" if r2.status_code in [200,201] else f"ERROR {r2.status_code}: {r2.text[:100]}")

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
    log("Done! ✅")
