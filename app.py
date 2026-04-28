"""
Tracker de Salud — Multi-usuario
Login con usuario + contraseña. Cada usuario guarda en su propio Google Sheet.
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
    page_title="Tracker de Salud",
    page_icon="🏃",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ─── TIMEZONE FIX (Panama = UTC-5, sin DST) ──────────────────────────────────
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
        "display_name": st.secrets.get("display_names", {}).get("esposa", "Mi esposa"),
        "emoji": "🌿",
    },
}


def check_password(username: str, password: str) -> bool:
    if username not in USERS:
        return False
    hashed = hashlib.sha256(password.encode()).hexdigest()
    return hashed == USERS[username]["password_hash"]


def login_screen():
    st.markdown("<br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("## 🏃 Tracker de Salud")
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

HEADERS = {
    "Suplementos": [
        "timestamp", "fecha", "NAC", "Mg_Glicinato", "Quercetina",
        "Creatina", "Electrolitos_running", "nota_NAC", "nota_Mg",
        "nota_Quercetina", "nota_Creatina", "nota_Electrolitos", "notas_generales",
    ],
    "Alimentacion": [
        "timestamp", "fecha", "hora", "tipo_comida", "alimentos",
        "reacciones_digestivas", "reacciones_energia", "reacciones_piel", "notas",
    ],
    "Bienestar": [
        "timestamp", "fecha", "hora_dormir", "hora_despertar", "horas_sueno",
        "calidad_sueno", "interrupciones", "sensacion_despertar",
        "energia_AM", "energia_PM", "animo", "foco", "estres", "agua_vasos",
        "recuperacion_muscular", "dolor_muscular", "zona_dolor",
        "sintomas_GI", "otros_sintomas", "notas",
    ],
    "Entrenamiento": [
        "timestamp", "fecha", "hora", "tipo_sesion", "duracion_min", "RPE",
        "rendimiento", "piriforme", "run_km", "run_desnivel_m",
        "run_tiempo", "run_FC_bpm", "fuerza_ejercicios", "notas",
    ],
}


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
    """Crea las hojas que no existan. Solo corre una vez por sesión."""
    sh = get_spreadsheet(spreadsheet_id)
    existing = [ws.title for ws in sh.worksheets()]
    for sheet_name, headers in HEADERS.items():
        if sheet_name not in existing:
            ws = sh.add_worksheet(title=sheet_name, rows=1000, cols=len(headers))
            ws.append_row(headers)


def get_or_create_worksheet(spreadsheet_id: str, sheet_name: str, headers: list):
    sh = get_spreadsheet(spreadsheet_id)
    try:
        return sh.worksheet(sheet_name)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=sheet_name, rows=1000, cols=len(headers))
        ws.append_row(headers)
        return ws


def append_row(ws, row: list):
    ws.append_row(row, value_input_option="USER_ENTERED")


def multi_select_tags(label, options, key, default=None):
    return st.multiselect(label, options, default=default or [], key=key)


@st.cache_data(ttl=60)
def get_all_records(spreadsheet_id: str, sheet_name: str) -> list[dict]:
    """Lee todos los registros. Cacheado 60s para evitar 429."""
    try:
        gc = get_gspread_client()
        sh = gc.open_by_key(spreadsheet_id)
        ws = sh.worksheet(sheet_name)
        return ws.get_all_records()
    except Exception:
        return []


# ─── MAIN ─────────────────────────────────────────────────────────────────────
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

if not st.session_state["logged_in"]:
    login_screen()
    st.stop()

# Usuario autenticado
user = st.session_state["user"]
spreadsheet_id = user["spreadsheet_id"]

# Init hojas — una sola vez por sesión, sin loop de llamadas repetidas
init_worksheets(spreadsheet_id)

# ─── HEADER ──────────────────────────────────────────────────────────────────
col1, col2 = st.columns([3, 1])
with col1:
    st.markdown(f"## {user['emoji']} Tracker de Salud — {user['display_name']}")
    st.caption("Registros para consulta de medicina funcional — 18 mayo 2026")
with col2:
    if st.button("Cerrar sesión", key="logout"):
        for key in ["logged_in", "username", "user"]:
            st.session_state[key] = None
        st.session_state["logged_in"] = False
        st.rerun()

fecha_hoy = st.date_input("📅 Fecha del registro", value=today_panama())
fecha_str = fecha_hoy.strftime("%Y-%m-%d")
st.divider()

tab_dash, tab_supps, tab_food, tab_wellness, tab_train = st.tabs([
    "📊 Dashboard", "💊 Suplementos", "🥦 Alimentación", "🌙 Bienestar", "🏋️ Entrenamiento"
])


# ═══════════════════════════════════════════════════════════
# TAB 0 — DASHBOARD
# ═══════════════════════════════════════════════════════════
with tab_dash:
    if st.button("🔄 Refrescar datos", key="refresh"):
        st.cache_data.clear()
        st.rerun()

    st.subheader(f"Resumen de hoy · {fecha_hoy.strftime('%A %d de %B')}")

    records_supp  = get_all_records(spreadsheet_id, "Suplementos")
    records_food  = get_all_records(spreadsheet_id, "Alimentacion")
    records_well  = get_all_records(spreadsheet_id, "Bienestar")
    records_train = get_all_records(spreadsheet_id, "Entrenamiento")

    supp_hoy  = [r for r in records_supp  if r.get("fecha") == fecha_str]
    food_hoy  = [r for r in records_food  if r.get("fecha") == fecha_str]
    well_hoy  = [r for r in records_well  if r.get("fecha") == fecha_str]
    train_hoy = [r for r in records_train if r.get("fecha") == fecha_str]

    # ── Checklist del día ──────────────────────────────────
    st.markdown("#### ✅ Checklist del día")

    comidas_hoy = {r.get("tipo_comida", "") for r in food_hoy}
    checks = {
        "Desayuno":         "Desayuno" in comidas_hoy,
        "Almuerzo":         "Almuerzo" in comidas_hoy,
        "Cena":             "Cena" in comidas_hoy,
        "Suplementos":      len(supp_hoy) > 0,
        "Entrenamiento":    len(train_hoy) > 0,
        "Bienestar diario": len(well_hoy) > 0,
    }

    total_done = sum(checks.values())
    pct = int(total_done / len(checks) * 100)
    st.progress(pct / 100, text=f"{pct}% completado hoy ({total_done}/{len(checks)})")
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

    # ── Resumen del día ─────────────────────────────────────
    st.markdown("#### 📋 Resumen del día")
    col1, col2 = st.columns(2)

    with col1:
        if food_hoy:
            comidas_list = ", ".join(r.get("tipo_comida", "") for r in food_hoy)
            st.markdown(f"🍽 **{len(food_hoy)} comida(s):** {comidas_list}")
        else:
            st.markdown("🍽 Sin comidas registradas")

        if supp_hoy:
            r = supp_hoy[-1]
            tomados = [k for k in ["NAC", "Mg_Glicinato", "Quercetina", "Creatina", "Electrolitos_running"] if r.get(k) == "SÍ"]
            st.markdown(f"💊 **Suplementos:** {', '.join(tomados) if tomados else 'ninguno marcado'}")
        else:
            st.markdown("💊 Suplementos no registrados")

    with col2:
        if train_hoy:
            r = train_hoy[-1]
            st.markdown(f"🏋️ **{r.get('tipo_sesion','')}** · {r.get('duracion_min','')} min · RPE {r.get('RPE','')}")
            piri = r.get("piriforme", "—")
            piri_color = "red" if "dolor" in piri or "parar" in piri else "green"
            st.markdown(f"Piriforme: :{piri_color}[{piri}]")
        else:
            st.markdown("🏋️ Sin entrenamiento registrado")

        if well_hoy:
            r = well_hoy[-1]
            st.markdown(
                f"😴 Sueño **{r.get('calidad_sueno','—')}/5** · "
                f"Energía AM **{r.get('energia_AM','—')}/10** · "
                f"Agua **{r.get('agua_vasos','—')} vasos**"
            )
        else:
            st.markdown("😴 Bienestar no registrado")

    st.divider()

    # ── Tendencias 7 días ──────────────────────────────────
    st.markdown("#### 📈 Últimos 7 días")

    last_7 = [(fecha_hoy - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(6, -1, -1)]

    energia_vals, sueno_vals = [], []
    for d in last_7:
        rows = [r for r in records_well if r.get("fecha") == d]
        if rows:
            r = rows[-1]
            try:
                energia_vals.append((d, int(r.get("energia_AM", 0))))
                sueno_vals.append((d, int(r.get("calidad_sueno", 0))))
            except (ValueError, TypeError):
                pass

    sesiones_semana = sum(1 for d in last_7 if any(r.get("fecha") == d for r in records_train))
    comidas_semana  = sum(1 for r in records_food if r.get("fecha", "") in last_7)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        avg_e = round(sum(v for _, v in energia_vals) / len(energia_vals), 1) if energia_vals else None
        st.metric("Energía AM prom.", f"{avg_e}/10" if avg_e else "—")
    with c2:
        avg_s = round(sum(v for _, v in sueno_vals) / len(sueno_vals), 1) if sueno_vals else None
        st.metric("Sueño prom.", f"{avg_s}/5" if avg_s else "—")
    with c3:
        st.metric("Sesiones de entreno", f"{sesiones_semana} días")
    with c4:
        st.metric("Comidas registradas", comidas_semana)

    if energia_vals:
        st.markdown("**Energía AM por día**")
        df_e = pd.DataFrame(energia_vals, columns=["fecha", "Energía AM"])
        df_e["fecha"] = df_e["fecha"].str[5:]
        st.bar_chart(df_e.set_index("fecha"), height=180, use_container_width=True)

    piri_semana = [(r.get("fecha", ""), r.get("piriforme", "")) for r in records_train if r.get("fecha", "") in last_7]
    if piri_semana:
        st.markdown("**Piriforme esta semana:**")
        for d, p in piri_semana:
            color = "red" if "dolor" in p or "parar" in p else "green"
            st.markdown(f"- {d}: :{color}[{p}]")


# ═══════════════════════════════════════════════════════════
# TAB 1 — SUPLEMENTOS
# ═══════════════════════════════════════════════════════════
with tab_supps:
    st.subheader("Check-in de suplementos")
    st.caption("Marca lo que tomaste hoy y anota sensaciones.")

    col1, col2 = st.columns(2)
    with col1:
        nac = st.checkbox("NAC (N-Acetil Cisteína)", key="s_nac")
        nota_nac = st.text_input("Nota NAC", placeholder="sensación, hora exacta...", key="n_nac") if nac else ""

        mg = st.checkbox("Magnesio Glicinato", key="s_mg")
        nota_mg = st.text_input("Nota Mg Glicinato", placeholder="calidad del sueño, relajación...", key="n_mg") if mg else ""

        querc = st.checkbox("Quercetina", key="s_querc")
        nota_querc = st.text_input("Nota Quercetina", placeholder="sensación...", key="n_querc") if querc else ""

    with col2:
        creat = st.checkbox("Creatina", key="s_creat")
        nota_creat = st.text_input("Nota Creatina", placeholder="pump, rendimiento...", key="n_creat") if creat else ""

        elec = st.checkbox("Electrolitos (running)", key="s_elec", help="Sodio 1g · Potasio 200mg · Mg 60mg")
        nota_elec = st.text_input("Nota Electrolitos", placeholder="distancia, condiciones, calambres...", key="n_elec") if elec else ""

    st.caption("Electrolitos: Na+ 1000 mg · K+ 200 mg · Mg²+ 60 mg por sesión de running")
    notas_gen_s = st.text_area("Notas generales", key="notas_supps",
                                placeholder="cambios en el protocolo, sensaciones generales...")

    if st.button("💾 Guardar check-in de suplementos", type="primary", key="btn_supps"):
        with st.spinner("Guardando..."):
            ws = get_or_create_worksheet(spreadsheet_id, "Suplementos", HEADERS["Suplementos"])
            append_row(ws, [
                ts(), fecha_str,
                "SÍ" if nac else "NO",
                "SÍ" if mg else "NO",
                "SÍ" if querc else "NO",
                "SÍ" if creat else "NO",
                "SÍ" if elec else "NO",
                nota_nac, nota_mg, nota_querc, nota_creat, nota_elec,
                notas_gen_s,
            ])
        st.success("✅ Check-in guardado")


# ═══════════════════════════════════════════════════════════
# TAB 2 — ALIMENTACIÓN
# ═══════════════════════════════════════════════════════════
with tab_food:
    st.subheader("Registro de comida")

    col1, col2 = st.columns(2)
    with col1:
        tipo_comida = st.selectbox("Tipo de comida", [
            "Desayuno", "Almuerzo", "Cena",
            "Merienda AM", "Merienda PM", "Pre-entreno", "Post-entreno",
        ], key="f_tipo")
    with col2:
        hora_comida = st.time_input("Hora", value=now_panama().time(), key="f_hora")

    alimentos = st.text_area(
        "Alimentos (uno por línea: alimento, cantidad, cocción, marca)",
        placeholder="arroz integral, 150g, cocido\npollo, 180g, a la plancha\nbrócolí, 100g, al vapor",
        height=120, key="f_alimentos",
    )

    st.markdown("**Reacciones percibidas** (hasta 2h después)")
    reac_dig = multi_select_tags("Digestivas",
        ["sin síntomas", "distensión", "gases", "reflujo", "náuseas", "diarrea", "estreñimiento", "dolor abdominal"],
        key="f_dig", default=["sin síntomas"])
    reac_energy = multi_select_tags("Energía y ánimo",
        ["energía estable", "pico de energía", "bajón post-comida", "somnolencia", "irritabilidad", "ansiedad", "foco mental", "niebla mental"],
        key="f_energy", default=["energía estable"])
    reac_skin = multi_select_tags("Piel / sistémicos",
        ["sin cambios", "picazón", "urticaria", "enrojecimiento", "congestión nasal", "cefalea", "fatiga inusual", "dolor muscular"],
        key="f_skin", default=["sin cambios"])

    notas_comida = st.text_area("Notas (contexto, hambre previa, velocidad al comer...)", key="f_notas")

    if st.button("💾 Guardar comida", type="primary", key="btn_food"):
        with st.spinner("Guardando..."):
            ws = get_or_create_worksheet(spreadsheet_id, "Alimentacion", HEADERS["Alimentacion"])
            append_row(ws, [
                ts(), fecha_str, str(hora_comida), tipo_comida,
                alimentos.replace("\n", " | "),
                ", ".join(reac_dig), ", ".join(reac_energy), ", ".join(reac_skin),
                notas_comida,
            ])
        st.success("✅ Comida guardada")


# ═══════════════════════════════════════════════════════════
# TAB 3 — BIENESTAR
# ═══════════════════════════════════════════════════════════
with tab_wellness:
    st.subheader("Bienestar diario")

    st.markdown("**Sueño**")
    col1, col2, col3 = st.columns(3)
    with col1:
        hora_dormir = st.time_input("Me dormí a las", key="w_sin")
        hora_despertar = st.time_input("Desperté a las", key="w_sout")
    with col2:
        horas_sueno = st.number_input("Horas estimadas", min_value=0.0, max_value=14.0,
                                       value=7.5, step=0.5, key="w_hrs")
        calidad_sueno = st.select_slider("Calidad del sueño", options=[1, 2, 3, 4, 5],
                                          value=3, key="w_calidad",
                                          format_func=lambda x: "★" * x)
    with col3:
        interrupciones = st.selectbox("Interrupciones", ["ninguna", "1 vez", "2 veces", "3+ veces"], key="w_wk")
        sensacion = st.selectbox("Sensación al despertar", ["descansado", "moderado", "cansado", "exhausto"], key="w_sf")

    st.divider()
    st.markdown("**Energía y estado mental**")
    col1, col2 = st.columns(2)
    with col1:
        energia_am = st.slider("Energía AM (1–10)", 1, 10, 7, key="w_eam")
        energia_pm = st.slider("Energía PM (1–10)", 1, 10, 6, key="w_epm")
    with col2:
        animo = st.selectbox("Estado de ánimo",
            ["excelente", "bueno", "neutral", "bajo", "irritable", "ansioso", "deprimido"], key="w_mood")
        foco = st.selectbox("Foco / concentración",
            ["muy buena", "buena", "regular", "pobre", "niebla mental"], key="w_foco")
        estres = st.selectbox("Estrés percibido", ["bajo", "moderado", "alto", "muy alto"], key="w_stress")
    agua = st.number_input("Agua (vasos)", min_value=0, max_value=20, value=8, key="w_water")

    st.divider()
    st.markdown("**Recuperación y síntomas físicos**")
    col1, col2 = st.columns(2)
    with col1:
        recuperacion = st.slider("Recuperación muscular (1–10)", 1, 10, 7, key="w_rec")
        dolor = st.selectbox("Dolor / rigidez muscular", ["ninguno", "leve", "moderado", "intenso"], key="w_sore")
        zona_dolor = st.text_input("Zona afectada", placeholder="piriforme derecho, gemelos...", key="w_zona")
    with col2:
        gut = st.selectbox("Síntomas GI del día", [
            "sin síntomas", "distensión leve", "gases", "reflujo",
            "diarrea", "estreñimiento", "múltiples síntomas"
        ], key="w_gut")
        otros = st.text_input("Otros síntomas", placeholder="cefalea, hormigueo, palpitaciones...", key="w_otros")

    notas_wellness = st.text_area("Notas del día", key="w_notas")

    if st.button("💾 Guardar bienestar del día", type="primary", key="btn_well"):
        with st.spinner("Guardando..."):
            ws = get_or_create_worksheet(spreadsheet_id, "Bienestar", HEADERS["Bienestar"])
            append_row(ws, [
                ts(), fecha_str,
                str(hora_dormir), str(hora_despertar), horas_sueno,
                calidad_sueno, interrupciones, sensacion,
                energia_am, energia_pm, animo, foco, estres, agua,
                recuperacion, dolor, zona_dolor, gut, otros, notas_wellness,
            ])
        st.success("✅ Bienestar del día guardado")


# ═══════════════════════════════════════════════════════════
# TAB 4 — ENTRENAMIENTO
# ═══════════════════════════════════════════════════════════
with tab_train:
    st.subheader("Log de entrenamiento")

    col1, col2, col3 = st.columns(3)
    with col1:
        tipo_sesion = st.selectbox("Tipo de sesión", [
            "Fuerza — piernas", "Fuerza — upper", "Fuerza — combinado",
            "Trail running", "Carrera en pista / asfalto",
            "Potencia / explosivo", "Movilidad / recuperación activa", "Descanso activo",
        ], key="t_tipo")
    with col2:
        duracion = st.number_input("Duración (min)", min_value=0, max_value=300, value=60, key="t_dur")
    with col3:
        hora_train = st.time_input("Hora de inicio", key="t_hora")

    col1, col2, col3 = st.columns(3)
    with col1:
        rpe = st.slider("RPE (1–10)", 1, 10, 7, key="t_rpe",
                        help="1 = muy fácil · 10 = máximo esfuerzo")
    with col2:
        rendimiento = st.selectbox("Rendimiento vs expectativa", [
            "superó expectativa", "según lo planeado", "por debajo", "sesión comprometida"
        ], key="t_perf")
    with col3:
        piriforme = st.selectbox("Piriforme durante sesión", [
            "sin molestia", "leve incomodidad", "dolor moderado", "tuve que parar"
        ], key="t_piri")

    if piriforme in ["dolor moderado", "tuve que parar"]:
        st.warning("⚠️ Considera aplicar el protocolo de recuperación.")

    st.divider()
    st.markdown("**Si fue carrera**")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        run_km = st.number_input("Distancia (km)", min_value=0.0, step=0.1, key="t_km")
    with col2:
        run_elev = st.number_input("Desnivel + (m)", min_value=0, key="t_elev")
    with col3:
        run_tiempo = st.text_input("Tiempo (mm:ss)", placeholder="55:30", key="t_time")
    with col4:
        run_hr = st.number_input("FC promedio (bpm)", min_value=0, key="t_hr")

    st.divider()
    st.markdown("**Si fue fuerza — ejercicios clave**")
    st.caption("Formato: Ejercicio | Series×Reps | Peso kg | Nota")
    fuerza_log = st.text_area(
        "Ejercicios",
        placeholder="Sentadilla trasera | 4×8 | 90kg | buena activación\nPress banca | 4×8 | 70kg | ok\nPeso muerto | 3×6 | 110kg | leve fatiga lumbar",
        height=120, key="t_fuerza",
    )
    notas_train = st.text_area("Sensaciones post-entreno", key="t_notas",
                                placeholder="bombeo, fatiga, dolor articular, energía después...")

    if st.button("💾 Guardar sesión de entrenamiento", type="primary", key="btn_train"):
        with st.spinner("Guardando..."):
            ws = get_or_create_worksheet(spreadsheet_id, "Entrenamiento", HEADERS["Entrenamiento"])
            append_row(ws, [
                ts(), fecha_str, str(hora_train),
                tipo_sesion, duracion, rpe, rendimiento, piriforme,
                run_km if run_km > 0 else "",
                run_elev if run_elev > 0 else "",
                run_tiempo,
                run_hr if run_hr > 0 else "",
                fuerza_log.replace("\n", " | "),
                notas_train,
            ])
        st.success("✅ Sesión guardada")


# ─── FOOTER ──────────────────────────────────────────────────────────────────
st.divider()
st.caption(f"💡 Datos de {user['display_name']} · Suplementos · Alimentacion · Bienestar · Entrenamiento")