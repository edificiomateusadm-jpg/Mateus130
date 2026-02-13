import streamlit as st
import requests
import pandas as pd
import time
import random
from datetime import datetime

# --- CONFIGURACIÓN TÉCNICA ---
IMG_BB_API_KEY = "4d082bcad64d3390228ec3d92cdc15c3"
FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLScsT1z4dK51DHmbH797A8KEDZP7s4R6FX_xmVTBCew2vGIbQA/formResponse"
ID_SHEET = "1FvnEi2HI4xjJg7IwYmhxPQESV8OaQrOZEfxmCXwSUx4"
GID_USUARIOS = "284650027"
GID_RESPUESTAS = "57989524"

# IDs de Google Form - REVISA QUE ESTOS SIGAN SIENDO LOS MISMOS EN TU GOOGLE FORM
ENTRY_DPTO = "entry.496848869"
ENTRY_MONTO = "entry.1553105788"
ENTRY_TIPO = "entry.1626552330"
ENTRY_MES = "entry.550569407"
ENTRY_LINK = "entry.791154903"
ENTRY_NOTAS = "entry.2019103542"

# --- CAPA DE DATOS ---
def fetch_data(gid):
    cache_breaker = random.randint(1, 999999)
    url = f"https://docs.google.com/spreadsheets/d/{ID_SHEET}/export?format=csv&gid={gid}&cache={cache_breaker}"
    try:
        df = pd.read_csv(url)
        if str(gid) == GID_RESPUESTAS:
            df.columns = ['Timestamp', 'Dpto', 'Monto', 'Tipo', 'Mes_Anio', 'Link', 'Notas']
            df['Timestamp'] = pd.to_datetime(df['Timestamp'], errors='coerce')
        return df
    except Exception as e:
        return pd.DataFrame()

def post_to_google(payload):
    # BLINDAJE: Convertimos todo a string, quitamos espacios y aseguramos que no haya vacíos
    data_to_send = {}
    for k, v in payload.items():
        val = str(v).strip()
        data_to_send[k] = val if val and val != "nan" else "N/A"
    
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "Mozilla/5.0"
    }
    
    try:
        # Usamos el parámetro 'timeout' para evitar que la app se cuelgue
        res = requests.post(FORM_URL, data=data_to_send, headers=headers, timeout=10)
        if res.status_code != 200:
            st.error(f"Error 400: Google rechazó los datos. Revisa si el formulario tiene 'Limitar a 1 respuesta' activo.")
        return res.status_code == 200
    except Exception as e:
        st.error(f"Error de conexión: {e}")
        return False

def get_latest_state(df, dpto, mes_anio):
    if df is None or df.empty: return "SIN_DEUDA", 0.0, None
    dpto_str = str(dpto).strip()
    mes_anio_str = str(mes_anio).strip()
    
    # 1. Deuda
    deuda_row = df[(df['Dpto'].astype(str) == dpto_str) & (df['Tipo'] == "COBRO_MENSUAL") & (df['Mes_Anio'] == mes_anio_str)]
    monto_deuda = float(deuda_row.iloc[-1]['Monto']) if not deuda_row.empty else 0.0
    
    # 2. Último Pago
    pagos = df[(df['Dpto'].astype(str) == dpto_str) & (df['Tipo'] == "PAGO_VECINO") & (df['Mes_Anio'] == mes_anio_str)]
    
    if not pagos.empty:
        ultimo_pago = pagos.iloc[-1]
        ts_pago = ultimo_pago['Timestamp']
        # 3. Validación
        validaciones = df[(df['Dpto'].astype(str) == dpto_str) & (df['Tipo'] == "VALIDACION_ADMIN") & 
                          (df['Mes_Anio'] == mes_anio_str) & (df['Timestamp'] > ts_pago)]
        
        if not validaciones.empty:
            return str(validaciones.iloc[-1]['Notas']).upper(), monto_deuda, None
        return "PENDIENTE", monto_deuda, ultimo_pago['Link']
            
    return "DEUDA_EXISTENTE" if monto_deuda > 0 else "SIN_DEUDA", monto_deuda, None

# --- UI ---
st.set_page_config(page_title="Edificio Pro", layout="wide")
if 'auth' not in st.session_state: st.session_state.auth = False

if not st.session_state.auth:
    st.title("🏢 Acceso")
    db_users = fetch_data(GID_USUARIOS)
    if not db_users.empty:
        user_sel = st.selectbox("Unidad", db_users['Dpto'].unique())
        pwd_sel = st.text_input("Pass", type="password")
        if st.button("Entrar"):
            real_pass = str(db_users[db_users['Dpto'].astype(str) == str(user_sel)]['Password'].values[0])
            if str(pwd_sel) == real_pass:
                st.session_state.auth, st.session_state.user = True, user_sel
                st.rerun()
            else: st.error("❌ Error")
else:
    is_admin = "ADMIN" in str(st.session_state.user).upper()
    menu = ["Dashboard", "Validar Pagos", "Cargar Deudas"] if is_admin else ["Dashboard", "Registrar Pago"]
    choice = st.sidebar.selectbox("Menú", menu)
    st.sidebar.button("Salir", on_click=lambda: st.session_state.update({"auth": False}))

    if choice == "Dashboard":
        st.title(f"👋 Hola, {st.session_state.user}")
        st.info("Selecciona una opción del menú.")

    elif is_admin and choice == "Validar Pagos":
        st.header("🔍 Validar")
        df_main = fetch_data(GID_RESPUESTAS)
        if not df_main.empty:
            pendientes = df_main[df_main['Tipo'] == "PAGO_VECINO"]
            for d in pendientes['Dpto'].unique():
                for m_a in pendientes[pendientes['Dpto'] == d]['Mes_Anio'].unique():
                    est, mon, lnk = get_latest_state(df_main, d, m_a)
                    if est == "PENDIENTE":
                        with st.expander(f"Dpto {d} - {m_a}"):
                            st.image(lnk, width=300)
                            if st.button(f"✅ Aprobar {d}", key=f"ap_{d}_{m_a}"):
                                if post_to_google({ENTRY_DPTO: d, ENTRY_MONTO: mon, ENTRY_TIPO: "VALIDACION_ADMIN", ENTRY_MES: m_a, ENTRY_NOTAS: "APROBADO"}):
                                    st.rerun()
                            if st.button(f"❌ Rechazar {d}", key=f"re_{d}_{m_a}"):
                                if post_to_google({ENTRY_DPTO: d, ENTRY_MONTO: mon, ENTRY_TIPO: "VALIDACION_ADMIN", ENTRY_MES: m_a, ENTRY_NOTAS: "RECHAZADO"}):
                                    st.rerun()

    elif is_admin and choice == "Cargar Deudas":
        st.header("📈 Cargar Deudas")
        c1, c2 = st.columns(2)
        mes = c1.selectbox("Mes", ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"])
        anio = c2.selectbox("Año", [2025, 2026, 2027])
        mes_anio = f"{mes} {anio}"
        df_main = fetch_data(GID_RESPUESTAS)
        dptos = ["101","102","201","202","301","302","401","402","501","502","601","602","701","702","801"]
        vals = [get_latest_state(df_main, d, mes_anio)[1] for d in dptos]
        df_edit = st.data_editor(pd.DataFrame({'Dpto': dptos, 'Monto': vals}), hide_index=True)
        if st.button("🚀 Publicar"):
            for i, row in df_edit.iterrows():
                post_to_google({ENTRY_DPTO: row['Dpto'], ENTRY_MONTO: row['Monto'], ENTRY_TIPO: "COBRO_MENSUAL", ENTRY_MES: mes_anio, ENTRY_NOTAS: "Carga"})
            st.success("Publicado")
            time.sleep(2)
            st.rerun()

    elif not is_admin and choice == "Registrar Pago":
        st.header("📝 Mi Pago")
        c1, c2 = st.columns(2)
        mes_v = c1.selectbox("Mes", ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"])
        anio_v = c2.selectbox("Año", [2025, 2026, 2027], index=1)
        mes_anio_v = f"{mes_v} {anio_v}"
        df_main = fetch_data(GID_RESPUESTAS)
        est, mon, lnk = get_latest_state(df_main, st.session_state.user, mes_anio_v)
        
        if est == "APROBADO": st.success(f"✅ Aprobado: ${mon}")
        elif est == "PENDIENTE": st.warning(f"⏳ Pendiente: ${mon}")
        elif mon > 0:
            if est == "RECHAZADO": st.error("❌ Rechazado. Reintenta.")
            st.info(f"Deuda: ${mon}")
            foto = st.file_uploader("Voucher", type=['jpg', 'png', 'jpeg'])
            if st.button("Enviar") and foto:
                img_url = requests.post(f"https://api.imgbb.com/1/upload?key={IMG_BB_API_KEY}", files={"image": foto}).json()['data']['url']
                if post_to_google({ENTRY_DPTO: st.session_state.user, ENTRY_MONTO: mon, ENTRY_TIPO: "PAGO_VECINO", ENTRY_MES: mes_anio_v, ENTRY_LINK: img_url}):
                    st.success("Enviado")
                    time.sleep(2)
                    st.rerun()
        else: st.warning("Sin deuda cargada.")
