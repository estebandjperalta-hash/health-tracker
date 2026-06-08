"""
Tracker de Alimentación & Suplementos — Multi-usuario
Hojas separadas por tiempo de comida + suplementos genérico.
"""

import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from datetime import date, datetime, timedelta
import hashlib
import pytz
import pandas as pd

# ─── PAGE CONFIG ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Tracker de Alimentación",
    page_icon="🥗",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ─── TIMEZONE (Panama = UTC-5, sin DST) ──────────────────────────────────────
TZ_PANAMA = pytz.timezone("America/Panama")

def now_panama() -> datetime:
    return datetime.now(TZ_PANAMA)

def today_panama() -> date:
    return now_panama().date()

def ts() -> str:
    return now_panama().strftime("%Y-%m-%d %H:%M:%S")

# ─── AUTH ─────────────────────────────────────────────────────────────────────
USERS = {
    "esteban": {
        "password_hash": hashlib.sha256(st.secrets["passwords"]["esteban"].encode()).hexdigest(),
        "spreadsheet_id": st.secrets["spreadsheets"]["esteban"],
        "display_name": "Esteban",
        "emoji": "🏃",
    },
    "esposa": {
        "password_hash": hashlib.sha256(st.secrets["passwords"]["esposa"].encode()).hexdigest(),
        "spreadsheet_id": st.secrets["spreadsheets"]["esposa"],
        "display_name": st.secrets.get("display_names", {}).get("esposa", "Ale"),
        "emoji": "🌿",
    },
}


def check_password(username: str, password: str) -> bool:
    if username not in USERS:
        return False
    return hashlib.sha256(password.encode()).hexdigest() == USERS[username]["password_hash"]


def login_screen():
    st.markdown("<br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("## 🥗 Tracker de Alimentación")
        st.caption("Consulta medicina funcional — 18 mayo 2026")
        st.markdown("<br>", unsafe_allow_html=True)
        with st.form("login_form"):
            username = st.selectbox("Usuario", ["esteban", "esposa"],
                                    format_func=lambda x: USERS[x]["display_name"])
            password = st.text_input("Contraseña", type="password")
            submitted = st.form_submit_button("Entrar", use_container_width=True, type="primary")
            if submitted:
                if check_password(username, password):
                    st.session_state["logged_in"] = True
                    st.session_state["username"] = username
                    st.session_state["user"] = USERS[username]
                    st.rerun()
                else:
                    st.error("Contraseña incorrecta")


# ─── GOOGLE SHEETS ───────────────────────────────────────────────────────────
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Columnas compartidas para todas las hojas de comida
FOOD_HEADERS = [
    "timestamp", "fecha", "hora",
    "alimentos", "cantidad_porcion",
    "reacciones_digestivas", "reacciones_energia", "reacciones_piel",
    "notas",
]

SUPP_HEADERS = [
    "timestamp", "fecha",
    "suplemento", "dosis", "hora_toma",
    "tomado", "nota",
]

# Nombres de hojas
MEAL_SHEETS = [
    "Desayuno",
    "Merienda_AM",
    "Almuerzo",
    "Merienda_PM",
    "Cena",
]

ALL_SHEETS = MEAL_SHEETS + ["Suplementos"]


@st.cache_resource(ttl=3600)
def get_gspread_client():
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"], scopes=SCOPES,
    )
    return gspread.authorize(creds)


@st.cache_resource(ttl=3600)
def get_spreadsheet(spreadsheet_id: str):
    gc = get_gspread_client()
    try:
        return gc.open_by_key(spreadsheet_id)
    except gspread.SpreadsheetNotFound:
        st.error(f"No se encontró el Spreadsheet con ID: {spreadsheet_id}")
        st.stop()


@st.cache_resource(ttl=3600)
def init_worksheets(spreadsheet_id: str):
    """Crea hojas faltantes. Corre una sola vez por sesión."""
    sh = get_spreadsheet(spreadsheet_id)
    existing = [ws.title for ws in sh.worksheets()]
    for sheet_name in MEAL_SHEETS:
        if sheet_name not in existing:
            ws = sh.add_worksheet(title=sheet_name, rows=1000, cols=len(FOOD_HEADERS))
            ws.append_row(FOOD_HEADERS)
    if "Suplementos" not in existing:
        ws = sh.add_worksheet(title="Suplementos", rows=1000, cols=len(SUPP_HEADERS))
        ws.append_row(SUPP_HEADERS)


def get_worksheet(spreadsheet_id: str, sheet_name: str):
    sh = get_spreadsheet(spreadsheet_id)
    return sh.worksheet(sheet_name)


def append_row(ws, row: list):
    ws.append_row(row, value_input_option="USER_ENTERED")


@st.cache_data(ttl=60)
def get_all_records(spreadsheet_id: str, sheet_name: str) -> list[dict]:
    try:
        gc = get_gspread_client()
        sh = gc.open_by_key(spreadsheet_id)
        ws = sh.worksheet(sheet_name)
        return ws.get_all_records()
    except Exception:
        return []


def multi_select_tags(label, options, key, default=None):
    return st.multiselect(label, options, default=default or [], key=key)


# ─── FORMULARIO DE COMIDA (reutilizable) ─────────────────────────────────────
def food_form(sheet_name: str, label: str, emoji: str, spreadsheet_id: str, fecha_str: str):
    st.subheader(f"{emoji} {label}")

    col1, col2 = st.columns(2)
    with col1:
        hora = st.time_input("Hora", value=now_panama().time(), key=f"{sheet_name}_hora")
    with col2:
        cantidad = st.text_input("Cantidad / porción general", placeholder="Ej: plato normal, 300g...",
                                  key=f"{sheet_name}_cantidad")

    alimentos = st.text_area(
        "Alimentos (uno por línea)",
        placeholder="arroz integral, 150g, cocido\npollo, 180g, plancha\naguacate, ½ unidad",
        height=110, key=f"{sheet_name}_alimentos",
    )

    st.markdown("**Reacciones percibidas**")
    reac_dig = multi_select_tags("Digestivas",
        ["sin síntomas", "distensión", "gases", "reflujo", "náuseas",
         "diarrea", "estreñimiento", "dolor abdominal"],
        key=f"{sheet_name}_dig", default=["sin síntomas"])
    reac_energy = multi_select_tags("Energía y ánimo",
        ["energía estable", "pico de energía", "bajón post-comida",
         "somnolencia", "irritabilidad", "ansiedad", "foco mental", "niebla mental"],
        key=f"{sheet_name}_energy", default=["energía estable"])
    reac_skin = multi_select_tags("Piel / sistémicos",
        ["sin cambios", "picazón", "urticaria", "enrojecimiento",
         "congestión nasal", "cefalea", "fatiga inusual", "dolor muscular"],
        key=f"{sheet_name}_skin", default=["sin cambios"])

    notas = st.text_area("Notas", placeholder="contexto, hambre previa, velocidad al comer...",
                          key=f"{sheet_name}_notas")

    if st.button(f"💾 Guardar {label}", type="primary", key=f"btn_{sheet_name}"):
        with st.spinner("Guardando..."):
            ws = get_worksheet(spreadsheet_id, sheet_name)
            append_row(ws, [
                ts(), fecha_str, str(hora),
                alimentos.replace("\n", " | "),
                cantidad,
                ", ".join(reac_dig),
                ", ".join(reac_energy),
                ", ".join(reac_skin),
                notas,
            ])
        st.success(f"✅ {label} guardado")
        st.cache_data.clear()


# ─── MAIN ─────────────────────────────────────────────────────────────────────
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

if not st.session_state["logged_in"]:
    login_screen()
    st.stop()

user = st.session_state["user"]
spreadsheet_id = user["spreadsheet_id"]

init_worksheets(spreadsheet_id)

# ─── HEADER ──────────────────────────────────────────────────────────────────
col1, col2 = st.columns([3, 1])
with col1:
    st.markdown(f"## {user['emoji']} Tracker — {user['display_name']}")
    st.caption("Registro de alimentación & suplementos · consulta medicina funcional")
with col2:
    if st.button("Cerrar sesión", key="logout"):
        for key in ["logged_in", "username", "user"]:
            st.session_state[key] = None
        st.session_state["logged_in"] = False
        st.rerun()

fecha_hoy = st.date_input("📅 Fecha del registro", value=today_panama())
fecha_str = fecha_hoy.strftime("%Y-%m-%d")
st.divider()

# ─── TABS ─────────────────────────────────────────────────────────────────────
tab_dash, tab_desayuno, tab_am, tab_almuerzo, tab_pm, tab_cena, tab_supps = st.tabs([
    "📊 Dashboard",
    "🌅 Desayuno",
    "🍎 Merienda AM",
    "🍽 Almuerzo",
    "🫐 Merienda PM",
    "🌙 Cena",
    "💊 Suplementos",
])


# ═══════════════════════════════════════════════════════════
# DASHBOARD
# ═══════════════════════════════════════════════════════════
with tab_dash:
    if st.button("🔄 Refrescar", key="refresh"):
        st.cache_data.clear()
        st.rerun()

    st.subheader(f"Resumen de hoy · {fecha_hoy.strftime('%A %d de %B')}")

    # Leer todas las hojas
    data = {s: get_all_records(spreadsheet_id, s) for s in ALL_SHEETS}

    # Registros de hoy
    hoy = {s: [r for r in data[s] if r.get("fecha") == fecha_str] for s in ALL_SHEETS}

    # ── Checklist ────────────────────────────────────────
    st.markdown("#### ✅ Checklist del día")

    checks = {
        "Desayuno":    len(hoy["Desayuno"]) > 0,
        "Merienda AM": len(hoy["Merienda_AM"]) > 0,
        "Almuerzo":    len(hoy["Almuerzo"]) > 0,
        "Merienda PM": len(hoy["Merienda_PM"]) > 0,
        "Cena":        len(hoy["Cena"]) > 0,
        "Suplementos": len(hoy["Suplementos"]) > 0,
    }

    total_done = sum(checks.values())
    pct = int(total_done / len(checks) * 100)
    st.progress(pct / 100, text=f"{pct}% registrado hoy ({total_done}/{len(checks)})")
    st.markdown("")

    cols = st.columns(3)
    for i, (label, done) in enumerate(checks.items()):
        with cols[i % 3]:
            icon = "✅" if done else "⏳"
            color = "green" if done else "orange"
            st.markdown(
                f":{color}[{icon} **{label}**]" if done else f":{color}[{icon} {label}]"
            )

    st.divider()

    # ── Resumen comidas de hoy ───────────────────────────
    st.markdown("#### 🍽 Lo que comiste hoy")

    meal_labels = {
        "Desayuno":    ("🌅", "Desayuno"),
        "Merienda_AM": ("🍎", "Merienda AM"),
        "Almuerzo":    ("🍽", "Almuerzo"),
        "Merienda_PM": ("🫐", "Merienda PM"),
        "Cena":        ("🌙", "Cena"),
    }

    any_food = False
    for sheet, (emoji, label) in meal_labels.items():
        registros = hoy[sheet]
        if registros:
            any_food = True
            r = registros[-1]
            alimentos_txt = r.get("alimentos", "—").replace(" | ", ", ")
            reac = r.get("reacciones_digestivas", "")
            reac_color = "red" if any(s in reac for s in ["distensión","gases","reflujo","náuseas","diarrea","dolor"]) else "green"
            st.markdown(f"**{emoji} {label}:** {alimentos_txt}")
            if reac and reac != "sin síntomas":
                st.markdown(f"  :{reac_color}[↳ {reac}]")
    if not any_food:
        st.caption("Sin comidas registradas aún hoy.")

    # Suplementos de hoy
    if hoy["Suplementos"]:
        st.divider()
        st.markdown("#### 💊 Suplementos de hoy")
        tomados = [r.get("suplemento","") for r in hoy["Suplementos"] if r.get("tomado","") == "SÍ"]
        no_tomados = [r.get("suplemento","") for r in hoy["Suplementos"] if r.get("tomado","") != "SÍ"]
        if tomados:
            st.markdown(f":green[✅ Tomados: {', '.join(tomados)}]")
        if no_tomados:
            st.markdown(f":orange[⏳ Pendientes: {', '.join(no_tomados)}]")

    st.divider()

    # ── Tendencias 7 días ────────────────────────────────
    st.markdown("#### 📈 Últimos 7 días")

    last_7 = [(fecha_hoy - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(6, -1, -1)]

    # Conteo de comidas por día
    meal_counts = []
    for d in last_7:
        count = sum(1 for s in MEAL_SHEETS if any(r.get("fecha") == d for r in data[s]))
        meal_counts.append((d[5:], count))  # MM-DD

    supp_counts = []
    for d in last_7:
        count = sum(1 for r in data["Suplementos"] if r.get("fecha") == d and r.get("tomado") == "SÍ")
        supp_counts.append((d[5:], count))

    c1, c2 = st.columns(2)
    with c1:
        avg_meals = round(sum(v for _, v in meal_counts) / len(meal_counts), 1)
        st.metric("Comidas registradas / día (prom.)", avg_meals)
    with c2:
        total_supps = sum(v for _, v in supp_counts)
        st.metric("Tomas de suplementos (semana)", total_supps)

    if any(v > 0 for _, v in meal_counts):
        st.markdown("**Comidas registradas por día**")
        df = pd.DataFrame(meal_counts, columns=["fecha", "Comidas"])
        st.bar_chart(df.set_index("fecha"), height=160, use_container_width=True)

    # Reacciones frecuentes esta semana
    all_reacciones = []
    for s in MEAL_SHEETS:
        for r in data[s]:
            if r.get("fecha", "") in last_7:
                reac = r.get("reacciones_digestivas", "")
                if reac and reac != "sin síntomas":
                    all_reacciones.extend([x.strip() for x in reac.split(",")])

    if all_reacciones:
        from collections import Counter
        top = Counter(all_reacciones).most_common(5)
        st.markdown("**Reacciones más frecuentes esta semana:**")
        for reac, count in top:
            st.markdown(f"- {reac}: **{count}x**")


# ═══════════════════════════════════════════════════════════
# TABS DE COMIDA
# ═══════════════════════════════════════════════════════════
with tab_desayuno:
    food_form("Desayuno", "Desayuno", "🌅", spreadsheet_id, fecha_str)

with tab_am:
    food_form("Merienda_AM", "Merienda AM", "🍎", spreadsheet_id, fecha_str)

with tab_almuerzo:
    food_form("Almuerzo", "Almuerzo", "🍽", spreadsheet_id, fecha_str)

with tab_pm:
    food_form("Merienda_PM", "Merienda PM", "🫐", spreadsheet_id, fecha_str)

with tab_cena:
    food_form("Cena", "Cena", "🌙", spreadsheet_id, fecha_str)


# ─── LISTA DE SUPLEMENTOS POR USUARIO ────────────────────────────────────────
SUPLEMENTOS_ESTEBAN = [
    {"nombre": "NAC",                  "dosis": "600 mg",     "instruccion": "1x día · noche"},
    {"nombre": "Quercetina",           "dosis": "500 mg",     "instruccion": "2x día"},
    {"nombre": "Cúrcuma",              "dosis": "1000 mg",    "instruccion": "1x día · con comida"},
    {"nombre": "Omega 3",              "dosis": "1000 mg",    "instruccion": "2x día · con comida"},
    {"nombre": "Colágeno",             "dosis": "10 g",       "instruccion": "1x día"},
    {"nombre": "Magnesio Glicinato",   "dosis": "300 mg",     "instruccion": "1x día · noche"},
    {"nombre": "Hierro",               "dosis": "30 mg",      "instruccion": "1x día · ayunas o entre comidas"},
    {"nombre": "Vitamina D3 + K2",     "dosis": "5000 UI",    "instruccion": "1x día"},
]

# ═══════════════════════════════════════════════════════════
# SUPLEMENTOS
# ═══════════════════════════════════════════════════════════
with tab_supps:
    st.subheader("💊 Suplementos del día")

    username = st.session_state.get("username", "")

    # ── ESTEBAN: checklist predefinida ────────────────────
    if username == "esteban":
        st.caption("Marca los que tomaste hoy y agrega nota si es necesario.")

        supps_guardados_hoy = get_all_records(spreadsheet_id, "Suplementos")
        supps_guardados_hoy = [r for r in supps_guardados_hoy if r.get("fecha") == fecha_str]
        ya_guardados = {r.get("suplemento", "") for r in supps_guardados_hoy}

        checks_supp = {}
        notas_supp = {}

        for s in SUPLEMENTOS_ESTEBAN:
            nombre = s["nombre"]
            ya = nombre in ya_guardados
            with st.expander(
                f"{'✅' if ya else '⬜'} **{nombre}** — {s['dosis']} · {s['instruccion']}",
                expanded=not ya,
            ):
                if ya:
                    r = next((x for x in supps_guardados_hoy if x.get("suplemento") == nombre), {})
                    st.success(f"Registrado a las {r.get('hora_toma', '—')}")
                    if r.get("nota"):
                        st.caption(f"Nota: {r.get('nota')}")
                else:
                    checks_supp[nombre] = st.checkbox("Lo tomé hoy", key=f"chk_{nombre}")
                    notas_supp[nombre] = st.text_input(
                        "Nota (opcional)", placeholder="sensación, hora exacta...",
                        key=f"nota_{nombre}", label_visibility="collapsed"
                    )

        st.markdown("")
        if st.button("💾 Guardar check-in de suplementos", type="primary", key="btn_supp_esteban"):
            pendientes = [s for s in SUPLEMENTOS_ESTEBAN if s["nombre"] not in ya_guardados]
            if not any(checks_supp.get(s["nombre"]) for s in pendientes):
                st.warning("Marca al menos un suplemento.")
            else:
                with st.spinner("Guardando..."):
                    ws = get_worksheet(spreadsheet_id, "Suplementos")
                    for s in pendientes:
                        nombre = s["nombre"]
                        if checks_supp.get(nombre):
                            append_row(ws, [
                                ts(), fecha_str,
                                nombre, s["dosis"],
                                str(now_panama().time()),
                                "SÍ",
                                notas_supp.get(nombre, ""),
                            ])
                st.success("✅ Check-in guardado")
                st.cache_data.clear()
                st.rerun()

    # ── ALE: entrada libre ────────────────────────────────
    else:
        st.caption("Registra cada suplemento por separado.")

        col1, col2, col3 = st.columns(3)
        with col1:
            suplemento = st.text_input("Suplemento", placeholder="Magnesio, Vitamina C...",
                                        key="supp_nombre")
            dosis = st.text_input("Dosis", placeholder="1 cápsula, 500 mg...", key="supp_dosis")
        with col2:
            tomado = st.radio("¿Lo tomaste?", ["SÍ", "NO"], horizontal=True, key="supp_tomado")
            hora_supp = st.time_input("Hora de toma", value=now_panama().time(), key="supp_hora")
        with col3:
            nota_supp = st.text_area("Nota", placeholder="sensación, con comida...",
                                      height=100, key="supp_nota")

        if st.button("💾 Guardar suplemento", type="primary", key="btn_supp_ale"):
            if not suplemento.strip():
                st.warning("Escribe el nombre del suplemento.")
            else:
                with st.spinner("Guardando..."):
                    ws = get_worksheet(spreadsheet_id, "Suplementos")
                    append_row(ws, [
                        ts(), fecha_str,
                        suplemento.strip(), dosis.strip(),
                        str(hora_supp), tomado, nota_supp,
                    ])
                st.success(f"✅ {suplemento} guardado")
                st.cache_data.clear()

        # Registros de hoy
        st.divider()
        st.markdown("**Registrado hoy:**")
        supps_hoy = get_all_records(spreadsheet_id, "Suplementos")
        supps_hoy = [r for r in supps_hoy if r.get("fecha") == fecha_str]
        if supps_hoy:
            for r in supps_hoy:
                color = "green" if r.get("tomado") == "SÍ" else "orange"
                nota = f" — {r.get('nota')}" if r.get("nota") else ""
                st.markdown(
                    f":{color}[{'✅' if r.get('tomado')=='SÍ' else '⏳'} "
                    f"**{r.get('suplemento','')}** {r.get('dosis','')}]{nota}"
                )
        else:
            st.caption("Sin registros de suplementos hoy.")


# ─── FOOTER ──────────────────────────────────────────────────────────────────
st.divider()
st.caption(f"💡 {user['display_name']} · Desayuno · Merienda AM · Almuerzo · Merienda PM · Cena · Suplementos")