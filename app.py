import streamlit as st
import requests
import pandas as pd
from datetime import datetime

# --- CONFIGURACIÓN TÉCNICA ---
IMG_BB_API_KEY = "4d082bcad64d3390228ec3d92cdc15c3"
FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLScsT1z4dK51DHmbH797A8KEDZP7s4R6FX_xmVTBCew2vGIbQA/formResponse"
SHEET_USUARIOS_URL = "https://docs.google.com/spreadsheets/d/1FvnEi2HI4xjJg7IwYmhxPQESV8OaQrOZEfxmCXwSUx4/export?format=csv&gid=284650027"
GID_RESPUESTAS = "57989524" 
SHEET_DATA_URL = f"https://docs.google.com/spreadsheets/d/1FvnEi2HI4xjJg7IwYmhxPQESV8OaQrOZEfxmCXwSUx4/export?format=csv&gid={GID_RESPUESTAS}"

# IDs de Google Form
ENTRY_DPTO, ENTRY_MONTO, ENTRY_TIPO, ENTRY_MES, ENTRY_LINK, ENTRY_NOTAS = (
    "entry.496848869", "entry.1553105788", "entry.1626552330", 
    "entry.550569407", "entry.791154903", "entry.2019103542"
)

# --- CAPA DE DATOS CON CACHÉ ---
@st.cache_data(ttl=10) # Cache de 10 segundos para evitar re-lecturas lentas
def fetch_data(url):
    try:
        df = pd.read_csv(url)
        if "export" in url and "gid=" + GID_RESPUESTAS in url:
            df.columns = ['Timestamp', 'Dpto', 'Monto', 'Tipo', 'Mes_Anio', 'Link', 'Notas']
            df['Timestamp'] = pd.to_datetime(df['Timestamp'], errors='coerce')
        return df
    except Exception as e:
        return pd.DataFrame()

def post_to_google(payload):
    # Forzamos que todo sea string y limpiamos espacios. 
    # Google Forms da Error 400 si recibe un campo que no reconoce o un valor nulo.
    clean_data = {str(k): str(v) if v is not None else " " for k, v in payload.items()}
    try:
        res = requests.post(FORM_URL, data=clean_data, timeout=10)
        return res.status_code == 200
    except:
        return False

def get_latest_state(df, dpto, mes_anio):
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
    db_users = fetch_data(SHEET_USUARIOS_URL)
    if not db_users.empty:
        user = st.selectbox("Seleccione su Unidad", db_users['Dpto'].unique(), key="login_user")
        pwd = st.text_input("Contraseña", type="password", key="login_pass")
        if st.button("Entrar"):
            real_pass = str(db_users[db_users['Dpto'].astype(str) == str(user)]['Password'].values[0])
            if str(pwd) == real_pass:
                st.session_state.auth = True
                st.session_state.user = user
                st.rerun()
            else: st.error("Contraseña incorrecta")
    else: st.info("Conectando con la base de datos...")

# --- APLICACIÓN ---
else:
    is_admin = "ADMIN" in str(st.session_state.user).upper()
    menu = ["Dashboard", "Validar Pagos", "Cargar Deudas"] if is_admin else ["Dashboard", "Registrar Pago"]
    choice = st.sidebar.selectbox("Menú", menu)
    
    if st.sidebar.button("Cerrar Sesión"):
        st.session_state.auth = False
        st.rerun()

    # 1. DASHBOARD
    if choice == "Dashboard":
        st.title(f"🏢 Panel: {st.session_state.user}")
        st.write(f"Fecha: {datetime.now().strftime('%d/%m/%Y')}")
        st.info("Utilice el menú lateral para navegar.")

    # 2. VALIDAR PAGOS (ADMIN)
    elif is_admin and choice == "Validar Pagos":
        st.header("🔍 Pagos por Revisar")
        df_main = fetch_data(SHEET_DATA_URL)
        if not df_main.empty:
            pendientes = df_main[df_main['Tipo'] == "PAGO_VECINO"]
            for d in pendientes['Dpto'].unique():
                for m in pendientes[pendientes['Dpto']==d]['Mes_Anio'].unique():
                    est, mon, lnk = get_latest_state(df_main, d, m)
                    if est == "PENDIENTE":
                        with st.expander(f"Dpto {d} - {m}"):
                            st.image(lnk, width=300)
                            ca, cb = st.columns(2)
                            if ca.button("Aprobar", key=f"ap_{d}_{m}"):
                                if post_to_google({ENTRY_DPTO: d, ENTRY_MONTO: mon, ENTRY_TIPO: "VALIDACION_ADMIN", ENTRY_MES: m, ENTRY_NOTAS: "APROBADO"}):
                                    st.cache_data.clear()
                                    st.rerun()
                            if cb.button("Rechazar", key=f"re_{d}_{m}"):
                                if post_to_google({ENTRY_DPTO: d, ENTRY_MONTO: mon, ENTRY_TIPO: "VALIDACION_ADMIN", ENTRY_MES: m, ENTRY_NOTAS: "RECHAZADO"}):
                                    st.cache_data.clear()
                                    st.rerun()

    # 3. CARGAR DEUDAS (ADMIN)
    elif is_admin and choice == "Cargar Deudas":
        st.header("📈 Publicar Deudas")
        mes_anio = f"{st.selectbox('Mes', ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'])} 2026"
        df_main = fetch_data(SHEET_DATA_URL)
        dptos = ["101","102","201","202","301","302","401","402","501","502","601","602","701","702","801"]
        vals = [get_latest_state(df_main, d, mes_anio)[1] for d in dptos]
        df_edit = st.data_editor(pd.DataFrame({'Dpto': dptos, 'Monto': vals}), hide_index=True)
        
        if st.button("Guardar Todo"):
            if (df_edit['Monto'] <= 0).any(): st.error("No se permiten montos en 0.")
            else:
                for _, r in df_edit.iterrows():
                    post_to_google({ENTRY_DPTO: r['Dpto'], ENTRY_MONTO: r['Monto'], ENTRY_TIPO: "COBRO_MENSUAL", ENTRY_MES: mes_anio, ENTRY_NOTAS: "Carga"})
                st.cache_data.clear()
                st.success("Enviado")
                st.rerun()

    # 4. REGISTRAR PAGO (VECINO)
    elif not is_admin and choice == "Registrar Pago":
        st.header("💰 Registrar Pago")
        mes_anio_v = f"{st.selectbox('Mes', ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'])} 2026"
        df_main = fetch_data(SHEET_DATA_URL)
        est, mon, lnk = get_latest_state(df_main, st.session_state.user, mes_anio_v)
        
        if est == "APROBADO": st.success("Pago Aprobado ✅")
        elif est == "PENDIENTE": st.warning("En revisión ⏳")
        elif mon > 0:
            if est == "RECHAZADO": st.error("Rechazado. Subir de nuevo.")
            st.info(f"Deuda: ${mon}")
            foto = st.file_uploader("Foto Comprobante", type=['jpg','png','jpeg'])
            if st.button("Enviar") and foto:
                url = requests.post(f"https://api.imgbb.com/1/upload?key={IMG_BB_API_KEY}", files={"image": foto}).json()['data']['url']
                if post_to_google({ENTRY_DPTO: st.session_state.user, ENTRY_MONTO: mon, ENTRY_TIPO: "PAGO_VECINO", ENTRY_MES: mes_anio_v, ENTRY_LINK: url}):
                    st.cache_data.clear()
                    st.rerun()
        else: st.warning("Sin deuda cargada.")
