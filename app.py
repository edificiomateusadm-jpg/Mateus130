import streamlit as st
import requests
import base64
import pandas as pd
from datetime import datetime

# --- CONFIGURACIÓN TÉCNICA ---
IMG_BB_API_KEY = "4d082bcad64d3390228ec3d92cdc15c3"
FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLScsT1z4dK51DHmbH797A8KEDZP7s4R6FX_xmVTBCew2vGIbQA/formResponse"
SHEET_USUARIOS_URL = "https://docs.google.com/spreadsheets/d/1FvnEi2HI4xjJg7IwYmhxPQESV8OaQrOZEfxmCXwSUx4/export?format=csv&gid=284650027"
# RECUERDA: Verifica siempre el GID de la pestaña de respuestas en tu Sheet
GID_RESPUESTAS = "57989524" 
SHEET_DATA_URL = f"https://docs.google.com/spreadsheets/d/1FvnEi2HI4xjJg7IwYmhxPQESV8OaQrOZEfxmCXwSUx4/export?format=csv&gid={GID_RESPUESTAS}"

# IDs de Google Form
ENTRY_DPTO, ENTRY_MONTO, ENTRY_TIPO, ENTRY_MES, ENTRY_LINK, ENTRY_NOTAS = (
    "entry.496848869", "entry.1553105788", "entry.1626552330", 
    "entry.550569407", "entry.791154903", "entry.2019103542"
)

# --- CAPA DE DATOS ---
def fetch_data():
    try:
        # Usamos cache_data para no saturar a Google con peticiones en cada click
        df = pd.read_csv(SHEET_DATA_URL)
        df.columns = ['Timestamp', 'Dpto', 'Monto', 'Tipo', 'Mes_Anio', 'Link', 'Notas']
        df['Timestamp'] = pd.to_datetime(df['Timestamp'], errors='coerce')
        return df
    except Exception as e:
        st.error(f"Error de conexión: {e}")
        return pd.DataFrame()

def post_to_google(payload):
    # LIMPIEZA: Convertimos todo a String y evitamos campos vacíos
    clean_payload = {}
    for k, v in payload.items():
        if v is None or str(v).strip() == "":
            clean_payload[k] = "N/A"
        else:
            clean_payload[k] = str(v)
            
    res = requests.post(FORM_URL, data=clean_payload)
    return res.status_code == 200

def get_latest_state(dpto, mes_anio):
    df = fetch_data()
    if df.empty: return "SIN_DEUDA", 0, None
    
    # 1. Deuda
    deuda_row = df[(df['Dpto'].astype(str) == str(dpto)) & (df['Tipo'] == "COBRO_MENSUAL") & (df['Mes_Anio'] == mes_anio)]
    monto_deuda = float(deuda_row.iloc[-1]['Monto']) if not deuda_row.empty else 0
    
    # 2. Último Pago
    pagos = df[(df['Dpto'].astype(str) == str(dpto)) & (df['Tipo'] == "PAGO_VECINO") & (df['Mes_Anio'] == mes_anio)]
    
    if not pagos.empty:
        ultimo_pago = pagos.iloc[-1]
        ts_pago = ultimo_pago['Timestamp']
        
        # 3. Validación Posterior
        validaciones = df[(df['Dpto'].astype(str) == str(dpto)) & 
                          (df['Tipo'] == "VALIDACION_ADMIN") & 
                          (df['Mes_Anio'] == mes_anio) &
                          (df['Timestamp'] > ts_pago)]
        
        if not validaciones.empty:
            return str(validaciones.iloc[-1]['Notas']).upper(), monto_deuda, None
        return "PENDIENTE", monto_deuda, ultimo_pago['Link']
            
    return "DEUDA_EXISTENTE" if monto_deuda > 0 else "SIN_DEUDA", monto_deuda, None

# --- UI CONFIG ---
st.set_page_config(page_title="Gestión Edificio 2026", layout="wide")

if 'auth' not in st.session_state: st.session_state.auth = False

# --- LOGIN ---
if not st.session_state.auth:
    st.title("🏢 Acceso al Sistema")
    try:
        db_users = pd.read_csv(SHEET_USUARIOS_URL)
        user = st.selectbox("Seleccione su Unidad", db_users['Dpto'].unique())
        pwd = st.text_input("Contraseña", type="password")
        if st.button("Entrar"):
            real_pass = str(db_users[db_users['Dpto'].astype(str) == str(user)]['Password'].values[0])
            if str(pwd) == real_pass:
                st.session_state.auth, st.session_state.user = True, user
                st.rerun()
            else: st.error("Contraseña incorrecta")
    except: st.info("Cargando base de usuarios...")

# --- APP ---
else:
    is_admin = "ADMIN" in str(st.session_state.user).upper()
    menu = ["Dashboard", "Validar Pagos", "Cargar Deudas"] if is_admin else ["Dashboard", "Registrar Pago"]
    choice = st.sidebar.selectbox("Menú", menu)
    st.sidebar.button("Cerrar Sesión", on_click=lambda: st.session_state.update({"auth": False}))

    # 1. DASHBOARD (Neutral / Aterrizaje)
    if choice == "Dashboard":
        st.title(f"🏢 Panel de Control - Unidad {st.session_state.user}")
        st.write(f"Hoy es {datetime.now().strftime('%d/%m/%Y')}")
        c1, c2 = st.columns(2)
        c1.metric("Estado de Conexión", "Óptimo ✅")
        c2.metric("Rol Detectado", "Administrador" if is_admin else "Propietario")
        st.divider()
        st.info("Seleccione una opción del menú lateral para operar el sistema.")

    # 2. VALIDAR PAGOS (ADMIN)
    elif is_admin and choice == "Validar Pagos":
        st.header("🔍 Pagos Pendientes de Revisión")
        df = fetch_data()
        if not df.empty:
            dptos_con_pagos = df[df['Tipo'] == "PAGO_VECINO"]['Dpto'].unique()
            hay_pendientes = False
            for d in dptos_con_pagos:
                for m in df[df['Dpto'].astype(str) == str(d)]['Mes_Anio'].unique():
                    estado, monto, link = get_latest_state(d, m)
                    if estado == "PENDIENTE":
                        hay_pendientes = True
                        with st.expander(f"Dpto {d} - {m} (${monto})"):
                            st.image(link, width=400)
                            col_a, col_b = st.columns(2)
                            if col_a.button("✅ Aprobar", key=f"ap_{d}_{m}"):
                                if post_to_google({ENTRY_DPTO: d, ENTRY_MONTO: monto, ENTRY_TIPO: "VALIDACION_ADMIN", ENTRY_MES: m, ENTRY_NOTAS: "APROBADO"}):
                                    st.rerun()
                            if col_b.button("❌ Rechazar", key=f"re_{d}_{m}"):
                                if post_to_google({ENTRY_DPTO: d, ENTRY_MONTO: monto, ENTRY_TIPO: "VALIDACION_ADMIN", ENTRY_MES: m, ENTRY_NOTAS: "RECHAZADO"}):
                                    st.rerun()
            if not hay_pendientes: st.success("Todo al día. No hay pagos pendientes.")

    # 3. CARGAR DEUDAS (ADMIN)
    elif is_admin and choice == "Cargar Deudas":
        st.header("📉 Publicar Deudas del Mes")
        mes_sel = st.selectbox("Mes", ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"])
        anio_sel = st.number_input("Año", value=2026)
        mes_anio = f"{mes_sel} {anio_sel}"
        
        dptos = ["101","102","201","202","301","302","401","402","501","502","601","602","701","702","801"]
        curr_vals = [get_latest_state(d, mes_anio)[1] for d in dptos]
        
        df_edit = st.data_editor(pd.DataFrame({'Dpto': dptos, 'Monto': curr_vals}), hide_index=True)
        
        if st.button("Publicar Todo"):
            # VALIDACIÓN: Impedir ceros o vacíos si se desea
            if df_edit['Monto'].isnull().any() or (df_edit['Monto'] == 0).any():
                st.error("⚠️ Error: Hay departamentos con monto 0 o vacío. Verifica los datos.")
            else:
                with st.spinner("Enviando..."):
                    for _, r in df_edit.iterrows():
                        post_to_google({ENTRY_DPTO: r['Dpto'], ENTRY_MONTO: r['Monto'], ENTRY_TIPO: "COBRO_MENSUAL", ENTRY_MES: mes_anio, ENTRY_NOTAS: "Carga Masiva"})
                    st.success("Datos publicados con éxito.")
                    st.rerun()

    # 4. REGISTRAR PAGO (VECINO)
    elif not is_admin and choice == "Registrar Pago":
        st.header("💰 Mis Pagos")
        mv = st.selectbox("Mes", ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"])
        av = st.number_input("Año", value=2026)
        mes_anio_v = f"{mv} {av}"
        
        est, mon, lnk = get_latest_state(st.session_state.user, mes_anio_v)
        
        if est == "APROBADO": st.success(f"✅ Pago de {mes_anio_v} por ${mon} APROBADO.")
        elif est == "PENDIENTE": st.warning(f"⏳ Pago de ${mon} en revisión. [Ver comprobante]({lnk})")
        elif mon > 0:
            if est == "RECHAZADO": st.error("❌ Pago anterior rechazado. Sube el correcto.")
            st.info(f"Deuda pendiente: **${mon}**")
            foto = st.file_uploader("Subir Comprobante", type=['jpg','png','jpeg'])
            if st.button("Registrar Pago Ahora") and foto:
                with st.spinner("Subiendo..."):
                    img_url = requests.post(f"https://api.imgbb.com/1/upload?key={IMG_BB_API_KEY}", files={"image": foto}).json()['data']['url']
                    if post_to_google({ENTRY_DPTO: st.session_state.user, ENTRY_MONTO: mon, ENTRY_TIPO: "PAGO_VECINO", ENTRY_MES: mes_anio_v, ENTRY_LINK: img_url}):
                        st.success("Pago enviado.")
                        st.rerun()
        else: st.warning("No hay deuda cargada para este mes.")
