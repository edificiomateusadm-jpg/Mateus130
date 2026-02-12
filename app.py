import streamlit as st
import requests
import pandas as pd
import time
import random
from datetime import datetime

# --- CONFIGURACIÓN TÉCNICA ---
IMG_BB_API_KEY = "4d082bcad64d3390228ec3d92cdc15c3"
FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLScsT1z4dK51DHmbH797A8KEDZP7s4R6FX_xmVTBCew2vGIbQA/formResponse"
SHEET_USUARIOS_URL = "https://docs.google.com/spreadsheets/d/1FvnEi2HI4xjJg7IwYmhxPQESV8OaQrOZEfxmCXwSUx4/export?format=csv&gid=284650027"
GID_RESPUESTAS = "57989524" 
ID_SHEET = "1FvnEi2HI4xjJg7IwYmhxPQESV8OaQrOZEfxmCXwSUx4"

# IDs de Google Form
ENTRY_DPTO, ENTRY_MONTO, ENTRY_TIPO, ENTRY_MES, ENTRY_LINK, ENTRY_NOTAS = (
    "entry.496848869", "entry.1553105788", "entry.1626552330", 
    "entry.550569407", "entry.791154903", "entry.2019103542"
)

# --- CAPA DE DATOS CON BYPASS DE CACHÉ ---
def fetch_data(gid):
    # Añadimos un número aleatorio al final de la URL para que Google no nos devuelva datos cacheados
    random_str = random.randint(1, 100000)
    url = f"https://docs.google.com/spreadsheets/d/{ID_SHEET}/export?format=csv&gid={gid}&cache_bypass={random_str}"
    try:
        df = pd.read_csv(url)
        if str(gid) == GID_RESPUESTAS:
            df.columns = ['Timestamp', 'Dpto', 'Monto', 'Tipo', 'Mes_Anio', 'Link', 'Notas']
            df['Timestamp'] = pd.to_datetime(df['Timestamp'], errors='coerce')
        return df
    except Exception as e:
        return pd.DataFrame()

def post_to_google(payload):
    clean_data = {str(k): str(v) if v is not None else " " for k, v in payload.items()}
    try:
        res = requests.post(FORM_URL, data=clean_data, timeout=10)
        return res.status_code == 200
    except:
        return False

def get_latest_state(df, dpto, mes_anio):
    if df is None or df.empty: return "SIN_DEUDA", 0, None
    
    # 1. Deuda
    deuda_row = df[(df['Dpto'].astype(str) == str(dpto)) & (df['Tipo'] == "COBRO_MENSUAL") & (df['Mes_Anio'] == mes_anio)]
    monto_deuda = float(deuda_row.iloc[-1]['Monto']) if not deuda_row.empty else 0
    
    # 2. Último Pago
    pagos = df[(df['Dpto'].astype(str) == str(dpto)) & (df['Tipo'] == "PAGO_VECINO") & (df['Mes_Anio'] == mes_anio)]
    
    if not pagos.empty:
        ultimo_pago = pagos.iloc[-1]
        ts_pago = ultimo_pago['Timestamp']
        validaciones = df[(df['Dpto'].astype(str) == str(dpto)) & (df['Tipo'] == "VALIDACION_ADMIN") & 
                          (df['Mes_Anio'] == mes_anio) & (df['Timestamp'] > ts_pago)]
        
        if not validaciones.empty:
            return str(validaciones.iloc[-1]['Notas']).upper(), monto_deuda, None
        return "PENDIENTE", monto_deuda, ultimo_pago['Link']
            
    return "DEUDA_EXISTENTE" if monto_deuda > 0 else "SIN_DEUDA", monto_deuda, None

# --- UI CONFIG ---
st.set_page_config(page_title="Sistema Edificio 2026", layout="wide")
if 'auth' not in st.session_state: st.session_state.auth = False

# --- LOGIN ---
if not st.session_state.auth:
    st.title("🏢 Acceso Administrativo")
    db_users = fetch_data("284650027")
    if not db_users.empty:
        user = st.selectbox("Unidad", db_users['Dpto'].unique())
        pwd = st.text_input("Contraseña", type="password")
        if st.button("Entrar"):
            real_pass = str(db_users[db_users['Dpto'].astype(str) == str(user)]['Password'].values[0])
            if str(pwd) == real_pass:
                st.session_state.auth, st.session_state.user = True, user
                st.rerun()
            else: st.error("❌ Contraseña incorrecta")
    else: st.info("Conectando con el servidor...")

else:
    is_admin = "ADMIN" in str(st.session_state.user).upper()
    menu = ["Dashboard", "Validar Pagos", "Cargar Deudas"] if is_admin else ["Dashboard", "Registrar Pago"]
    choice = st.sidebar.selectbox("Menú", menu)
    st.sidebar.button("Cerrar Sesión", on_click=lambda: st.session_state.update({"auth": False}))

    # --- 1. DASHBOARD ---
    if choice == "Dashboard":
        st.title(f"👋 Bienvenid@, {st.session_state.user}")
        st.info("Navegue usando el menú lateral.")

    # --- 2. VALIDAR PAGOS (ADMIN) ---
    elif is_admin and choice == "Validar Pagos":
        st.header("🔍 Validación de Pagos")
        df_main = fetch_data(GID_RESPUESTAS)
        pendientes = df_main[df_main['Tipo'] == "PAGO_VECINO"] if not df_main.empty else pd.DataFrame()
        encontrados = False
        if not pendientes.empty:
            for d in pendientes['Dpto'].unique():
                for m_a in pendientes[pendientes['Dpto']==d]['Mes_Anio'].unique():
                    est, mon, lnk = get_latest_state(df_main, d, m_a)
                    if est == "PENDIENTE":
                        encontrados = True
                        with st.expander(f"Dpto {d} - {m_a}"):
                            st.image(lnk, width=300)
                            ca, cb = st.columns(2)
                            if ca.button("✅ Aprobar", key=f"ap_{d}_{m_a}"):
                                if post_to_google({ENTRY_DPTO: d, ENTRY_MONTO: mon, ENTRY_TIPO: "VALIDACION_ADMIN", ENTRY_MES: m_a, ENTRY_NOTAS: "APROBADO"}):
                                    st.toast("Pago Aprobado")
                                    time.sleep(1)
                                    st.rerun()
                            if cb.button("❌ Rechazar", key=f"re_{d}_{m_a}"):
                                if post_to_google({ENTRY_DPTO: d, ENTRY_MONTO: mon, ENTRY_TIPO: "VALIDACION_ADMIN", ENTRY_MES: m_a, ENTRY_NOTAS: "RECHAZADO"}):
                                    st.toast("Pago Rechazado")
                                    time.sleep(1)
                                    st.rerun()
        if not encontrados: st.success("No hay pagos pendientes.")

    # --- 3. CARGAR DEUDAS (ADMIN) ---
    elif is_admin and choice == "Cargar Deudas":
        st.header("📈 Publicar Montos Mensuales")
        c1, c2 = st.columns(2)
        mes = c1.selectbox("Mes", ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"])
        anio = c2.selectbox("Año", [2025, 2026, 2027])
        mes_anio = f"{mes} {anio}"
        
        df_main = fetch_data(GID_RESPUESTAS)
        dptos = ["101","102","201","202","301","302","401","402","501","502","601","602","701","702","801"]
        vals = [get_latest_state(df_main, d, mes_anio)[1] for d in dptos]
        
        df_edit = st.data_editor(pd.DataFrame({'Dpto': dptos, 'Monto': vals}), hide_index=True, use_container_width=True)
        
        if st.button("🚀 Publicar Todo"):
            if (df_edit['Monto'] <= 0).any():
                st.error("❌ Los montos deben ser mayores a 0.")
            else:
                progress = st.progress(0)
                status_text = st.empty()
                success_count = 0
                for i, row in df_edit.iterrows():
                    status_text.text(f"Enviando Dpto {row['Dpto']}...")
                    if post_to_google({ENTRY_DPTO: row['Dpto'], ENTRY_MONTO: row['Monto'], ENTRY_TIPO: "COBRO_MENSUAL", ENTRY_MES: mes_anio, ENTRY_NOTAS: "Carga"}):
                        success_count += 1
                    progress.progress((i + 1) / len(df_edit))
                
                if success_count == len(df_edit):
                    status_text.empty()
                    st.success(f"✅ ¡Éxito! Se publicaron las deudas de {mes_anio}.")
                    time.sleep(2) # Pausa para que el ADMIN vea el mensaje
                    st.rerun()

    # --- 4. REGISTRAR PAGO (VECINO) ---
    elif not is_admin and choice == "Registrar Pago":
        st.header("📝 Registro de Pago")
        c1, c2 = st.columns(2)
        mes_v = c1.selectbox("Mes", ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"])
        anio_v = c2.selectbox("Año", [2025, 2026, 2027], index=1)
        mes_anio_v = f"{mes_v} {anio_v}"
        
        df_main = fetch_data(GID_RESPUESTAS)
        est, mon, lnk = get_latest_state(df_main, st.session_state.user, mes_anio_v)
        
        if est == "APROBADO": st.success(f"✅ Pago de {mes_anio_v} por ${mon} APROBADO.")
        elif est == "PENDIENTE": st.warning(f"⏳ Pago de {mes_anio_v} en revisión.")
        elif mon > 0:
            if est == "RECHAZADO": st.error("❌ Pago RECHAZADO. Sube uno nuevo.")
            st.info(f"Deuda para {mes_anio_v}: **${mon}**")
            foto = st.file_uploader("Voucher", type=['jpg','png','jpeg'])
            if st.button("Enviar Pago"):
                if foto:
                    with st.spinner("Subiendo..."):
                        res_img = requests.post(f"https://api.imgbb.com/1/upload?key={IMG_BB_API_KEY}", files={"image": foto}).json()
                        url = res_img['data']['url']
                        if post_to_google({ENTRY_DPTO: st.session_state.user, ENTRY_MONTO: mon, ENTRY_TIPO: "PAGO_VECINO", ENTRY_MES: mes_anio_v, ENTRY_LINK: url}):
                            st.success("✅ Pago enviado.")
                            time.sleep(2)
                            st.rerun()
        else: st.warning(f"⚠️ Sin deuda para {mes_anio_v}.")
