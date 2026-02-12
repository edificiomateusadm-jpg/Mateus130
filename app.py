import streamlit as st
import requests
import base64
import pandas as pd
from datetime import datetime

# --- CONFIGURACIÓN TÉCNICA ---
IMG_BB_API_KEY = "4d082bcad64d3390228ec3d92cdc15c3"
FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLScsT1z4dK51DHmbH797A8KEDZP7s4R6FX_xmVTBCew2vGIbQA/formResponse"
SHEET_USUARIOS_URL = "https://docs.google.com/spreadsheets/d/1FvnEi2HI4xjJg7IwYmhxPQESV8OaQrOZEfxmCXwSUx4/export?format=csv&gid=284650027"
# RECUERDA: Verifica que el GID de abajo sea el de la pestaña de respuestas
GID_RESPUESTAS = "57989524" # Asegúrate de que este sea el GID correcto de tus respuestas
SHEET_DATA_URL = f"https://docs.google.com/spreadsheets/d/1FvnEi2HI4xjJg7IwYmhxPQESV8OaQrOZEfxmCXwSUx4/export?format=csv&gid={GID_RESPUESTAS}"

# IDs de Google Form
ENTRY_DPTO, ENTRY_MONTO, ENTRY_TIPO, ENTRY_MES, ENTRY_LINK, ENTRY_NOTAS = (
    "entry.496848869", "entry.1553105788", "entry.1626552330", 
    "entry.550569407", "entry.791154903", "entry.2019103542"
)

# --- CAPA DE DATOS ---
def fetch_data():
    try:
        df = pd.read_csv(SHEET_DATA_URL)
        df.columns = ['Timestamp', 'Dpto', 'Monto', 'Tipo', 'Mes_Anio', 'Link', 'Notas']
        # Convertir Timestamp a datetime para comparaciones lógicas
        df['Timestamp'] = pd.to_datetime(df['Timestamp'], errors='coerce')
        return df
    except Exception as e:
        st.error(f"Error crítico de lectura: {e}")
        return pd.DataFrame()

def post_to_google(payload):
    return requests.post(FORM_URL, data=payload).status_code == 200

def get_latest_state(dpto, mes_anio):
    df = fetch_data()
    if df.empty: return "SIN_DEUDA", 0, None
    
    # 1. Buscar Deuda (Cobro)
    deuda_row = df[(df['Dpto'].astype(str) == str(dpto)) & (df['Tipo'] == "COBRO_MENSUAL") & (df['Mes_Anio'] == mes_anio)]
    monto_deuda = float(deuda_row.iloc[-1]['Monto']) if not deuda_row.empty else 0
    
    # 2. Buscar Último Pago del Vecino
    pagos = df[(df['Dpto'].astype(str) == str(dpto)) & (df['Tipo'] == "PAGO_VECINO") & (df['Mes_Anio'] == mes_anio)]
    
    if not pagos.empty:
        ultimo_pago = pagos.iloc[-1]
        ts_pago = ultimo_pago['Timestamp']
        
        # 3. Buscar si hay una Validación POSTERIOR a ese pago
        validaciones = df[(df['Dpto'].astype(str) == str(dpto)) & 
                          (df['Tipo'] == "VALIDACION_ADMIN") & 
                          (df['Mes_Anio'] == mes_anio) &
                          (df['Timestamp'] > ts_pago)]
        
        if not validaciones.empty:
            estado_val = str(validaciones.iloc[-1]['Notas']).upper()
            return estado_val, monto_deuda, None # APROBADO o RECHAZADO
        else:
            return "PENDIENTE", monto_deuda, ultimo_pago['Link']
            
    return "DEUDA_EXISTENTE" if monto_deuda > 0 else "SIN_DEUDA", monto_deuda, None

# --- UI CONFIG ---
st.set_page_config(page_title="Sistema Edificio Pro", layout="wide")

if 'auth' not in st.session_state: st.session_state.auth = False

# --- LOGIN ---
if not st.session_state.auth:
    st.title("🏢 Gestión de Finanzas - Edificio")
    try:
        db_users = pd.read_csv(SHEET_USUARIOS_URL)
        user_list = db_users['Dpto'].unique()
        user = st.selectbox("Unidad / Rol", user_list)
        pwd = st.text_input("Contraseña", type="password")
        if st.button("Ingresar"):
            real_pass = str(db_users[db_users['Dpto'].astype(str) == str(user)]['Password'].values[0])
            if str(pwd) == real_pass:
                st.session_state.auth, st.session_state.user = True, user
                st.rerun()
            else: st.error("Contraseña incorrecta")
    except: st.warning("Configurando conexión...")

# --- APP PRINCIPAL ---
else:
    is_admin = "ADMIN" in str(st.session_state.user).upper()
    menu = ["Validar Pagos", "Cargar Deudas", "Dashboard General"] if is_admin else ["Registrar Pago"]
    choice = st.sidebar.selectbox("Menú", menu)
    st.sidebar.write(f"Usuario: **{st.session_state.user}**")

    # --- FLUJO ADMIN: VALIDAR PAGOS ---
    if is_admin and choice == "Validar Pagos":
        st.header("🔍 Validación de Comprobantes Recibidos")
        df = fetch_data()
        if not df.empty:
            # Encontrar departamentos que tienen pagos pendientes
            dptos_con_pagos = df[df['Tipo'] == "PAGO_VECINO"]['Dpto'].unique()
            hay_pendientes = False
            
            for d in dptos_con_pagos:
                meses_intentados = df[(df['Dpto'].astype(str) == str(d)) & (df['Tipo'] == "PAGO_VECINO")]['Mes_Anio'].unique()
                for m in meses_intentados:
                    estado, monto, link = get_latest_state(d, m)
                    if estado == "PENDIENTE":
                        hay_pendientes = True
                        with st.expander(f"📦 PAGO POR VALIDAR: Dpto {d} - {m} (${monto})"):
                            st.image(link, caption="Comprobante subido por vecino", use_container_width=True)
                            c1, c2 = st.columns(2)
                            if c1.button("Aprobar Pago", key=f"ap_{d}_{m}"):
                                post_to_google({ENTRY_DPTO: d, ENTRY_MONTO: monto, ENTRY_TIPO: "VALIDACION_ADMIN", ENTRY_MES: m, ENTRY_NOTAS: "APROBADO"})
                                st.success(f"Dpto {d} aprobado.")
                                st.rerun()
                            if c2.button("Rechazar Pago", key=f"re_{d}_{m}"):
                                post_to_google({ENTRY_DPTO: d, ENTRY_MONTO: monto, ENTRY_TIPO: "VALIDACION_ADMIN", ENTRY_MES: m, ENTRY_NOTAS: "RECHAZADO"})
                                st.error(f"Dpto {d} rechazado.")
                                st.rerun()
            if not hay_pendientes: st.info("No hay pagos pendientes de revisión.")

    # --- FLUJO ADMIN: CARGAR DEUDAS ---
    elif is_admin and choice == "Cargar Deudas":
        st.header("📈 Configuración de Deudas Mensuales")
        m = st.selectbox("Mes", ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"])
        a = st.number_input("Año", value=2026)
        mes_anio = f"{m} {a}"
        
        dptos = ["101","102","201","202","301","302","401","402","501","502","601","602","701","702","801"]
        current_vals = []
        for d in dptos:
            _, monto, _ = get_latest_state(d, mes_anio)
            current_vals.append(monto)
            
        st.info("💡 Recuperamos montos previos automáticamente si existen.")
        df_editor = st.data_editor(pd.DataFrame({'Dpto': dptos, 'Monto': current_vals}), hide_index=True, use_container_width=True)
        
        if st.button("Guardar y Publicar Deudas"):
            with st.spinner("Actualizando base de datos..."):
                for _, r in df_editor.iterrows():
                    post_to_google({ENTRY_DPTO: r['Dpto'], ENTRY_MONTO: r['Monto'], ENTRY_TIPO: "COBRO_MENSUAL", ENTRY_MES: mes_anio, ENTRY_NOTAS: "Carga Sistema"})
                st.success(f"Cobros de {mes_anio} publicados.")
                st.rerun()

    # --- FLUJO VECINO: REGISTRAR PAGO ---
    elif not is_admin and choice == "Registrar Pago":
        st.header("💰 Estado de Cuenta y Registro")
        m_v = st.selectbox("Mes", ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"])
        a_v = st.number_input("Año", value=2026)
        mes_anio_v = f"{m_v} {a_v}"
        
        estado, monto, link = get_latest_state(st.session_state.user, mes_anio_v)
        
        if estado == "APROBADO":
            st.success(f"✅ ¡Pago Verificado! Tu cuota de {mes_anio_v} por ${monto} ha sido aprobada.")
            st.balloons()
        elif estado == "PENDIENTE":
            st.warning(f"⏳ Pago en Revisión. Tu comprobante por ${monto} está siendo validado por el administrador.")
            if st.button("Ver mi comprobante"): st.image(link)
        elif monto > 0:
            if estado == "RECHAZADO":
                st.error("❌ Tu comprobante anterior fue RECHAZADO. Por favor, sube la foto correcta.")
            st.info(f"Monto pendiente para {mes_anio_v}: **${monto}**")
            archivo = st.file_uploader("Sube la foto de tu comprobante de pago", type=['jpg','png','jpeg'])
            if st.button("Enviar Registro de Pago"):
                if archivo:
                    with st.spinner("Subiendo evidencia..."):
                        res_img = requests.post(f"https://api.imgbb.com/1/upload?key={IMG_BB_API_KEY}", files={"image": archivo}).json()
                        img_url = res_img['data']['url']
                        if post_to_google({ENTRY_DPTO: st.session_state.user, ENTRY_MONTO: monto, ENTRY_TIPO: "PAGO_VECINO", ENTRY_MES: mes_anio_v, ENTRY_LINK: img_url, ENTRY_NOTAS: "Subido por Vecino"}):
                            st.success("¡Pago enviado con éxito! Espera la validación del administrador.")
                            st.rerun()
                else: st.warning("Por favor, selecciona una imagen.")
        else:
            st.warning("⚠️ No se ha cargado deuda para este mes todavía. Consulta con el administrador.")

    if st.sidebar.button("Cerrar Sesión"):
        st.session_state.auth = False
        st.rerun()
