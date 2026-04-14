"""
Tracker de Salud — Esteban
Registra alimentación, suplementos, bienestar y entrenamiento.
Los datos se guardan en Google Sheets vía gspread.
"""

import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from datetime import date, datetime
import json
import pandas as pd

# ─── PAGE CONFIG ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Tracker de Salud",
    page_icon="🏃",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ─── GOOGLE SHEETS AUTH ──────────────────────────────────────────────────────
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

@st.cache_resource(ttl=600)
def get_gsheet_client():
    """
    Autentica con Google Sheets.
    Las credenciales vienen de st.secrets["gcp_service_account"].
    Ver README para cómo configurarlas.
    """
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=SCOPES,
    )
    return gspread.authorize(creds)


@st.cache_resource(ttl=600)
def get_all_worksheets(spreadsheet_id: str):
    gc = get_gsheet_client()
    sh = gc.open_by_key(spreadsheet_id)
    return sh

def get_or_create_worksheet(gc, spreadsheet_id: str, sheet_name: str, headers: list[str]):
    sh = get_all_worksheets(spreadsheet_id)
    try:
        ws = sh.worksheet(sheet_name)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=sheet_name, rows=1000, cols=len(headers))
        ws.append_row(headers)
    return ws
    """Devuelve la hoja; la crea con cabeceras si no existe."""
    try:
        sh = gc.open_by_key(spreadsheet_id)
    except gspread.SpreadsheetNotFound:
        st.error(f"No se encontró el Spreadsheet con ID: {spreadsheet_id}")
        st.stop()

    try:
        ws = sh.worksheet(sheet_name)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=sheet_name, rows=1000, cols=len(headers))
        ws.append_row(headers)

    # Si la hoja existe pero no tiene cabeceras aún, las agrega
    if ws.row_count == 0 or ws.cell(1, 1).value != headers[0]:
        ws.insert_row(headers, index=1)

    return ws


def append_row(ws, row: list):
    ws.append_row(row, value_input_option="USER_ENTERED")


# ─── SHEET HEADERS ───────────────────────────────────────────────────────────
HEADERS = {
    "Suplementos": [
        "timestamp", "fecha", "NAC", "Mg_Glicinato", "Quercetina",
        "Creatina", "Electrolitos_running", "nota_NAC", "nota_Mg",
        "nota_Quercetina", "nota_Creatina", "nota_Electrolitos", "notas_generales",
    ],
    "Alimentacion": [
        "timestamp", "fecha", "hora", "tipo_comida", "alimentos",
        "reacciones_digestivas", "reacciones_energia", "reacciones_piel",
        "notas",
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

# ─── HELPERS ─────────────────────────────────────────────────────────────────
def ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def multi_select_tags(label: str, options: list[str], key: str, default: list[str] = None):
    return st.multiselect(label, options, default=default or [], key=key)


# ─── SIDEBAR CONFIG ──────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Configuración")
    spreadsheet_id = st.text_input(
        "ID del Google Spreadsheet",
        value=st.secrets.get("spreadsheet_id", ""),
        help="El ID está en la URL: docs.google.com/spreadsheets/d/[ID]/edit",
    )
    st.caption("Asegúrate de compartir el Sheet con el service account email.")
    st.divider()
    st.caption("Tracker de Salud v1.0 · Consulta Dra. 18 mayo 2026")


# ─── MAIN ────────────────────────────────────────────────────────────────────
st.title("🏃 Tracker de Salud")
st.caption("Registros para consulta de medicina funcional — 18 mayo 2026")

if not spreadsheet_id:
    st.warning("Ingresa el ID de tu Google Spreadsheet en la barra lateral para continuar.")
    st.stop()

try:
    gc = get_gsheet_client()
except Exception as e:
    st.error(f"Error de autenticación con Google: {e}")
    st.stop()

# Init worksheets
for sheet_name, headers in HEADERS.items():
    get_or_create_worksheet(gc, spreadsheet_id, sheet_name, headers)

fecha_hoy = st.date_input("📅 Fecha del registro", value=date.today())
fecha_str = fecha_hoy.strftime("%Y-%m-%d")

st.divider()

tab_supps, tab_food, tab_wellness, tab_train = st.tabs([
    "💊 Suplementos", "🥦 Alimentación", "🌙 Bienestar", "🏋️ Entrenamiento"
])


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

        elec = st.checkbox("Electrolitos (running)", key="s_elec",
                           help="Sodio 1g · Potasio 200mg · Mg 60mg")
        nota_elec = st.text_input(
            "Nota Electrolitos", placeholder="distancia, condiciones climáticas, calambres...", key="n_elec"
        ) if elec else ""

    st.caption("Composición electrolitos: Na+ 1000 mg · K+ 200 mg · Mg²+ 60 mg por sesión de running")

    notas_gen_s = st.text_area("Notas generales de suplementación", key="notas_supps",
                                placeholder="cambios en el protocolo, sensaciones generales...")

    if st.button("💾 Guardar check-in de suplementos", type="primary", key="btn_supps"):
        with st.spinner("Guardando..."):
            ws = get_or_create_worksheet(gc, spreadsheet_id, "Suplementos", HEADERS["Suplementos"])
            row = [
                ts(), fecha_str,
                "SÍ" if nac else "NO",
                "SÍ" if mg else "NO",
                "SÍ" if querc else "NO",
                "SÍ" if creat else "NO",
                "SÍ" if elec else "NO",
                nota_nac, nota_mg, nota_querc, nota_creat, nota_elec,
                notas_gen_s,
            ]
            append_row(ws, row)
        st.success("✅ Check-in guardado en Google Sheets")


# ═══════════════════════════════════════════════════════════
# TAB 2 — ALIMENTACIÓN
# ═══════════════════════════════════════════════════════════
with tab_food:
    st.subheader("Registro de comida")

    col1, col2 = st.columns(2)
    with col1:
        tipo_comida = st.selectbox("Tipo de comida", [
            "Desayuno", "Almuerzo", "Cena",
            "Merienda AM", "Merienda PM",
            "Pre-entreno", "Post-entreno",
        ], key="f_tipo")
    with col2:
        hora_comida = st.time_input("Hora", value=datetime.now().time(), key="f_hora")

    st.markdown("**Alimentos consumidos**")
    alimentos = st.text_area(
        "Lista los alimentos (uno por línea: alimento, cantidad, cocción, marca)",
        placeholder="arroz integral, 150g, cocido\npollo, 180g, a la plancha, Macropollo\nbrócolí, 100g, al vapor",
        height=120,
        key="f_alimentos",
    )

    st.markdown("**Reacciones percibidas** (hasta 2h después)")

    reac_dig = multi_select_tags(
        "Digestivas",
        ["sin síntomas", "distensión", "gases", "reflujo", "náuseas", "diarrea", "estreñimiento", "dolor abdominal"],
        key="f_dig", default=["sin síntomas"],
    )
    reac_energy = multi_select_tags(
        "Energía y ánimo",
        ["energía estable", "pico de energía", "bajón post-comida", "somnolencia", "irritabilidad", "ansiedad", "foco mental", "niebla mental"],
        key="f_energy", default=["energía estable"],
    )
    reac_skin = multi_select_tags(
        "Piel / sistémicos",
        ["sin cambios", "picazón", "urticaria", "enrojecimiento", "congestión nasal", "cefalea", "fatiga inusual", "dolor muscular"],
        key="f_skin", default=["sin cambios"],
    )

    notas_comida = st.text_area("Notas (contexto, hambre previa, velocidad al comer...)", key="f_notas")

    if st.button("💾 Guardar comida", type="primary", key="btn_food"):
        with st.spinner("Guardando..."):
            ws = get_or_create_worksheet(gc, spreadsheet_id, "Alimentacion", HEADERS["Alimentacion"])
            row = [
                ts(), fecha_str,
                str(hora_comida), tipo_comida,
                alimentos.replace("\n", " | "),
                ", ".join(reac_dig),
                ", ".join(reac_energy),
                ", ".join(reac_skin),
                notas_comida,
            ]
            append_row(ws, row)
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
        horas_sueno = st.number_input("Horas estimadas", min_value=0.0, max_value=14.0, value=7.5, step=0.5, key="w_hrs")
        calidad_sueno = st.select_slider("Calidad del sueño", options=[1, 2, 3, 4, 5], value=3, key="w_calidad",
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
        animo = st.selectbox("Estado de ánimo", ["excelente", "bueno", "neutral", "bajo", "irritable", "ansioso", "deprimido"], key="w_mood")
        foco = st.selectbox("Foco / concentración", ["muy buena", "buena", "regular", "pobre", "niebla mental"], key="w_foco")
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
            ws = get_or_create_worksheet(gc, spreadsheet_id, "Bienestar", HEADERS["Bienestar"])
            row = [
                ts(), fecha_str,
                str(hora_dormir), str(hora_despertar), horas_sueno,
                calidad_sueno, interrupciones, sensacion,
                energia_am, energia_pm, animo, foco, estres, agua,
                recuperacion, dolor, zona_dolor, gut, otros, notas_wellness,
            ]
            append_row(ws, row)
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
                        help="Rate of Perceived Exertion: 1 muy fácil, 10 máximo esfuerzo")
    with col2:
        rendimiento = st.selectbox("Rendimiento vs expectativa", [
            "superó expectativa", "según lo planeado", "por debajo", "sesión comprometida"
        ], key="t_perf")
    with col3:
        piriforme = st.selectbox("Piriforme durante sesión", [
            "sin molestia", "leve incomodidad", "dolor moderado", "tuve que parar"
        ], key="t_piri")

    if piriforme in ["dolor moderado", "tuve que parar"]:
        st.warning("⚠️ Considera revisar el plan de esta semana y aplicar el protocolo de recuperación.")

    st.divider()
    st.markdown("**Si fue carrera**")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        run_km = st.number_input("Distancia (km)", min_value=0.0, step=0.1, key="t_km")
    with col2:
        run_elev = st.number_input("Desnivel + (m)", min_value=0, key="t_elev")
    with col3:
        run_tiempo = st.text_input("Tiempo total (mm:ss)", placeholder="55:30", key="t_time")
    with col4:
        run_hr = st.number_input("FC promedio (bpm)", min_value=0, key="t_hr")

    st.divider()
    st.markdown("**Si fue fuerza — ejercicios clave**")
    st.caption("Formato: Ejercicio | Series×Reps | Peso kg | Nota")
    fuerza_log = st.text_area(
        "Ejercicios",
        placeholder="Sentadilla trasera | 4×8 | 90kg | buena activación\nPress banca | 4×8 | 70kg | pecho bien activado\nPeso muerto | 3×6 | 110kg | espalda baja leve fatiga",
        height=130,
        key="t_fuerza",
    )

    notas_train = st.text_area("Sensaciones post-entreno", key="t_notas",
                                placeholder="bombeo, fatiga, dolor articular, energía después, ánimo post-sesión...")

    if st.button("💾 Guardar sesión de entrenamiento", type="primary", key="btn_train"):
        with st.spinner("Guardando..."):
            ws = get_or_create_worksheet(gc, spreadsheet_id, "Entrenamiento", HEADERS["Entrenamiento"])
            row = [
                ts(), fecha_str, str(hora_train),
                tipo_sesion, duracion, rpe, rendimiento, piriforme,
                run_km if run_km > 0 else "",
                run_elev if run_elev > 0 else "",
                run_tiempo,
                run_hr if run_hr > 0 else "",
                fuerza_log.replace("\n", " | "),
                notas_train,
            ]
            append_row(ws, row)
        st.success("✅ Sesión guardada")


# ─── FOOTER ──────────────────────────────────────────────────────────────────
st.divider()
st.caption("💡 Los datos se guardan en 4 hojas de tu Google Sheet: Suplementos · Alimentacion · Bienestar · Entrenamiento")
