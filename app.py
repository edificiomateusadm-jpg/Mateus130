import streamlit as st
import requests
import base64
import pandas as pd

# --- CONFIGURACIÓN TÉCNICA ---
IMG_BB_API_KEY = "4d082bcad64d3390228ec3d92cdc15c3"
FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLScsT1z4dK51DHmbH797A8KEDZP7s4R6FX_xmVTBCew2vGIbQA/formResponse"
SHEET_USUARIOS_URL = "https://docs.google.com/spreadsheets/d/1FvnEi2HI4xjJg7IwYmhxPQESV8OaQrOZEfxmCXwSUx4/export?format=csv&gid=284650027"
SHEET_DATA_URL = "https://docs.google.com/spreadsheets/d/1FvnEi2HI4xjJg7IwYmhxPQESV8OaQrOZEfxmCXwSUx4/export?format=csv&gid=0"

# IDs de Google Form
ENTRY_DPTO, ENTRY_MONTO, ENTRY_TIPO, ENTRY_MES, ENTRY_LINK, ENTRY_NOTAS = (
    "entry.496848869", "entry.1553105788", "entry.1626552330", 
    "entry.550569407", "entry.791154903", "entry.2019103542"
)

# --- CAPA DE DATOS ---
def fetch_data():
    try:
        df = pd.read_csv(SHEET_DATA_URL)
        # Limpieza de nombres de columnas para facilitar acceso por índice
        df.columns = ['Timestamp', 'Dpto', 'Monto', 'Tipo', 'Mes_Anio', 'Link', 'Notas']
        return df
    except: return pd.DataFrame()

def post_to_google(payload):
    return requests.post(FORM_URL, data=payload).status_code == 200

def get_latest_state(dpto, mes_anio):
    df = fetch_data()
    if df.empty: return "SIN_DEUDA", 0, None
    
    # 1. Buscar Deuda (Cobro)
    deuda_row = df[(df['Dpto'].astype(str) == str(dpto)) & (df['Tipo'] == "COBRO_MENSUAL") & (df['Mes_Anio'] == mes_anio)]
    monto_deuda = float(deuda_row.iloc[-1]['Monto']) if not deuda_row.empty else 0
    
    # 2. Buscar si hay Validación (Aprobado/Rechazado)
    valid_row = df[(df['Dpto'].astype(str) == str(dpto)) & (df['Tipo'] == "VALIDACION_ADMIN") & (df['Mes_Anio'] == mes_anio)]
    if not valid_row.empty:
        return valid_row.iloc[-1]['Notas'], monto_deuda, None # Retorna APROBADO o RECHAZADO
        
    # 3. Buscar si hay Pago Pendiente
    pago_row = df[(df['Dpto'].astype(str) == str(dpto)) & (df['Tipo'] == "PAGO_VECINO") & (df['Mes_Anio'] == mes_anio)]
    if not pago_row.empty:
        return "PENDIENTE", monto_deuda, pago_row.iloc[-1]['Link']
        
    return "DEUDA_EXISTENTE" if monto_deuda > 0 else "SIN_DEUDA", monto_deuda, None

# --- UI LOGIC ---
st.set_page_config(page_title="Admin Edificio Pro", layout="wide")

if 'auth' not in st.session_state: st.session_state.auth = False

if not st.session_state.auth:
    # Bloque de Login (Lectura desde SHEET_USUARIOS_URL)
    st.title("🏢 Backend Edificio")
    db_users = pd.read_csv(SHEET_USUARIOS_URL)
    user = st.selectbox("Unidad", db_users['Dpto'].unique())
    pwd = st.text_input("Pass", type="password")
    if st.button("Login"):
        if str(pwd) == str(db_users[db_users['Dpto'].astype(str) == str(user)]['Password'].values[0]):
            st.session_state.auth, st.session_state.user = True, user
            st.rerun()
else:
    is_admin = "ADMIN" in str(st.session_state.user).upper()
    menu = ["Dashboard", "Validar Pagos", "Cargar Deudas"] if is_admin else ["Estado de Cuenta", "Subir Pago"]
    choice = st.sidebar.selectbox("Menú", menu)

    # --- FLUJO ADMIN: VALIDACIÓN ---
    if is_admin and choice == "Validar Pagos":
        st.header("🔍 Validación de Comprobantes")
        df = fetch_data()
        # Filtrar solo pagos de vecinos que no tengan una validación posterior
        pagos_pendientes = df[df['Tipo'] == "PAGO_VECINO"]
        
        for _, pago in pagos_pendientes.iloc[::-1].head(10).iterrows(): # Ver los últimos 10
            # Verificar si ya fue validado
            estado, _, _ = get_latest_state(pago['Dpto'], pago['Mes_Anio'])
            if estado == "PENDIENTE":
                with st.expander(f"Dpto {pago['Dpto']} - {pago['Mes_Anio']} (${pago['Monto']})"):
                    st.image(pago['Link'], width=400)
                    c1, c2 = st.columns(2)
                    if c1.button("Aprobar", key=f"ap_{pago['Timestamp']}"):
                        post_to_google({ENTRY_DPTO: pago['Dpto'], ENTRY_MONTO: pago['Monto'], ENTRY_TIPO: "VALIDACION_ADMIN", ENTRY_MES: pago['Mes_Anio'], ENTRY_NOTAS: "APROBADO"})
                        st.rerun()
                    if c2.button("Rechazar", key=f"re_{pago['Timestamp']}"):
                        post_to_google({ENTRY_DPTO: pago['Dpto'], ENTRY_MONTO: pago['Monto'], ENTRY_TIPO: "VALIDACION_ADMIN", ENTRY_MES: pago['Mes_Anio'], ENTRY_NOTAS: "RECHAZADO"})
                        st.rerun()

    # --- FLUJO ADMIN: CARGA DE DEUDAS ---
    elif is_admin and choice == "Cargar Deudas":
        st.header("📈 Configuración de Cobros Mensuales")
        m = st.selectbox("Mes", ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"])
        a = st.number_input("Año", value=2026)
        mes_anio = f"{m} {a}"
        
        # Precarga de datos existentes para evitar empezar de cero
        df_prev = fetch_data()
        current_vals = []
        dptos = ["101","102","201","202","301","302","401","402","501","502","601","602","701","702","801"]
        for d in dptos:
            _, monto, _ = get_latest_state(d, mes_anio)
            current_vals.append(monto)
            
        df_editor = st.data_editor(pd.DataFrame({'Dpto': dptos, 'Monto': current_vals}), hide_index=True)
        
        if st.button("Publicar Cobros"):
            for _, r in df_editor.iterrows():
                post_to_google({ENTRY_DPTO: r['Dpto'], ENTRY_MONTO: r['Monto'], ENTRY_TIPO: "COBRO_MENSUAL", ENTRY_MES: mes_anio, ENTRY_NOTAS: "Carga Sistema"})
            st.success("Cobros actualizados.")

    # --- FLUJO VECINO ---
    elif not is_admin and choice == "Subir Pago":
        st.header("💰 Registrar Pago")
        m_v = st.selectbox("Mes", ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"])
        a_v = st.number_input("Año", value=2026)
        mes_anio_v = f"{m_v} {a_v}"
        
        estado, monto, link = get_latest_state(st.session_state.user, mes_anio_v)
        
        if estado == "APROBADO":
            st.success(f"✅ Tu pago de {mes_anio_v} por ${monto} ha sido aprobado.")
        elif estado == "PENDIENTE":
            st.warning(f"⏳ Pago de ${monto} en revisión. Puedes ver tu comprobante aquí: [Link]({link})")
        elif monto > 0:
            if estado == "RECHAZADO": st.error("❌ Pago anterior rechazado. Sube el correcto.")
            st.info(f"Monto a pagar: **${monto}**")
            archivo = st.file_uploader("Sube el comprobante")
            if st.button("Enviar"):
                if archivo:
                    with st.spinner("Subiendo..."):
                        img_url = requests.post(f"https://api.imgbb.com/1/upload?key={IMG_BB_API_KEY}", files={"image": archivo}).json()['data']['url']
                        post_to_google({ENTRY_DPTO: st.session_state.user, ENTRY_MONTO: monto, ENTRY_TIPO: "PAGO_VECINO", ENTRY_MES: mes_anio_v, ENTRY_LINK: img_url, ENTRY_NOTAS: ""})
                        st.success("Enviado con éxito")
                        st.rerun()
        else:
            st.warning("No hay deuda cargada para este mes.")

    if st.sidebar.button("Cerrar Sesión"):
        st.session_state.auth = False
        st.rerun()
