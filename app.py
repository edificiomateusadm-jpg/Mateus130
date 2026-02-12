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

# IDs de Google Form (Asegúrate de que sean los correctos de tu formulario)
ENTRY_DPTO = "entry.496848869"
ENTRY_MONTO = "entry.1553105788"
ENTRY_TIPO = "entry.1626552330"
ENTRY_MES = "entry.550569407"
ENTRY_LINK = "entry.791154903"
ENTRY_NOTAS = "entry.2019103542"

# --- CAPA DE DATOS CON BYPASS DE CACHÉ ---
def fetch_data(gid):
    # El cache_breaker obliga a Google a darnos los datos más recientes
    cache_breaker = random.randint(1, 999999)
    url = f"https://docs.google.com/spreadsheets/d/{ID_SHEET}/export?format=csv&gid={gid}&cache={cache_breaker}"
    try:
        df = pd.read_csv(url)
        if str(gid) == GID_RESPUESTAS:
            # Forzamos los nombres de columnas para que el resto del código no falle
            df.columns = ['Timestamp', 'Dpto', 'Monto', 'Tipo', 'Mes_Anio', 'Link', 'Notas']
            df['Timestamp'] = pd.to_datetime(df['Timestamp'], errors='coerce')
        return df
    except Exception as e:
        st.error(f"Error de conexión con el servidor de datos: {e}")
        return pd.DataFrame()

def post_to_google(payload):
    # Convertimos todo a texto para evitar errores 400
    clean_payload = {str(k): str(v) if v is not None else " " for k, v in payload.items()}
    try:
        res = requests.post(FORM_URL, data=clean_payload, timeout=10)
        return res.status_code == 200
    except:
        return False

def get_latest_state(df, dpto, mes_anio):
    if df is None or df.empty: return "SIN_DEUDA", 0.0, None
    
    # 1. Buscar Deuda (Cobro)
    deuda_row = df[(df['Dpto'].astype(str) == str(dpto)) & 
                   (df['Tipo'] == "COBRO_MENSUAL") & 
                   (df['Mes_Anio'] == str(mes_anio))]
    
    monto_deuda = float(deuda_row.iloc[-1]['Monto']) if not deuda_row.empty else 0.0
    
    # 2. Buscar Último Pago del Propietario
    pagos = df[(df['Dpto'].astype(str) == str(dpto)) & 
               (df['Tipo'] == "PAGO_VECINO") & 
               (df['Mes_Anio'] == str(mes_anio))]
    
    if not pagos.empty:
        ultimo_pago = pagos.iloc[-1]
        ts_pago = ultimo_pago['Timestamp']
        
        # 3. Buscar si hay una validación del Admin posterior a ese pago
        validaciones = df[(df['Dpto'].astype(str) == str(dpto)) & 
                          (df['Tipo'] == "VALIDACION_ADMIN") & 
                          (df['Mes_Anio'] == str(mes_anio)) & 
                          (df['Timestamp'] > ts_pago)]
        
        if not validaciones.empty:
            estado_v = str(validaciones.iloc[-1]['Notas']).upper()
            return estado_v, monto_deuda, None
        return "PENDIENTE", monto_deuda, ultimo_pago['Link']
            
    return "DEUDA_EXISTENTE" if monto_deuda > 0 else "SIN_DEUDA", monto_deuda, None

# --- UI CONFIG ---
st.set_page_config(page_title="Sistema Edificio 2026", layout="wide")
if 'auth' not in st.session_state: st.session_state.auth = False

# --- LOGIN ---
if not st.session_state.auth:
    st.title("🏢 Acceso Propietarios / Admin")
    db_users = fetch_data(GID_USUARIOS)
    if not db_users.empty:
        user_sel = st.selectbox("Seleccione su Unidad", db_users['Dpto'].unique())
        pwd_sel = st.text_input("Contraseña", type="password")
        if st.button("Ingresar"):
            real_pass = str(db_users[db_users['Dpto'].astype(str) == str(user_sel)]['Password'].values[0])
            if str(pwd_sel) == real_pass:
                st.session_state.auth = True
                st.session_state.user = user_sel
                st.rerun()
            else: st.error("❌ Contraseña incorrecta.")
    else: st.warning("Conectando con la base de datos de usuarios...")

else:
    is_admin = "ADMIN" in str(st.session_state.user).upper()
    menu = ["Dashboard", "Validar Pagos", "Cargar Deudas"] if is_admin else ["Dashboard", "Registrar Pago"]
    choice = st.sidebar.selectbox("Menú Principal", menu)
    
    if st.sidebar.button("Cerrar Sesión"):
        st.session_state.auth = False
        st.rerun()

    # --- DASHBOARD ---
    if choice == "Dashboard":
        st.title(f"👋 Panel de {st.session_state.user}")
        st.write(f"Fecha actual: {datetime.now().strftime('%d/%m/%Y')}")
        st.info("Utilice el menú de la izquierda para realizar operaciones.")

    # --- VALIDAR PAGOS (ADMIN) ---
    elif is_admin and choice == "Validar Pagos":
        st.header("🔍 Validación de Comprobantes")
        df_main = fetch_data(GID_RESPUESTAS)
        encontrados = False
        if not df_main.empty:
            pendientes = df_main[df_main['Tipo'] == "PAGO_VECINO"]
            for d in pendientes['Dpto'].unique():
                for m_a in pendientes[pendientes['Dpto'] == d]['Mes_Anio'].unique():
                    est, mon, lnk = get_latest_state(df_main, d, m_a)
                    if est == "PENDIENTE":
                        encontrados = True
                        with st.expander(f"🔴 PAGO PENDIENTE: Dpto {d} - {m_a}"):
                            st.image(lnk, caption="Voucher enviado", use_container_width=True)
                            c1, c2 = st.columns(2)
                            if c1.button("✅ Aprobar", key=f"ap_{d}_{m_a}"):
                                if post_to_google({ENTRY_DPTO: d, ENTRY_MONTO: mon, ENTRY_TIPO: "VALIDACION_ADMIN", ENTRY_MES: m_a, ENTRY_NOTAS: "APROBADO"}):
                                    st.toast("Pago aprobado con éxito")
                                    time.sleep(1)
                                    st.rerun()
                            if c2.button("❌ Rechazar", key=f"re_{d}_{m_a}"):
                                if post_to_google({ENTRY_DPTO: d, ENTRY_MONTO: mon, ENTRY_TIPO: "VALIDACION_ADMIN", ENTRY_MES: m_a, ENTRY_NOTAS: "RECHAZADO"}):
                                    st.toast("Pago rechazado")
                                    time.sleep(1)
                                    st.rerun()
        if not encontrados: st.success("No hay pagos pendientes de revisión.")

    # --- CARGAR DEUDAS (ADMIN) ---
    elif is_admin and choice == "Cargar Deudas":
        st.header("📈 Publicación de Deudas Mensuales")
        c1, c2 = st.columns(2)
        mes_s = c1.selectbox("Mes", ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"])
        anio_s = c2.selectbox("Año", [2025, 2026, 2027])
        mes_anio_full = f"{mes_s} {anio_s}"
        
        df_main = fetch_data(GID_RESPUESTAS)
        dptos_fijos = ["101","102","201","202","301","302","401","402","501","502","601","602","701","702","801"]
        vals_actuales = [get_latest_state(df_main, d, mes_anio_full)[1] for d in dptos_fijos]
        
        st.write(f"Editando cobros para: **{mes_anio_full}**")
        df_edit = st.data_editor(pd.DataFrame({'Dpto': dptos_fijos, 'Monto': vals_actuales}), hide_index=True, use_container_width=True)
        
        if st.button("🚀 Enviar Cobros al Sistema"):
            if (df_edit['Monto'] <= 0).any():
                st.error("⚠️ Error: Todos los departamentos deben tener un monto mayor a 0.")
            else:
                progress = st.progress(0)
                status = st.empty()
                for i, row in df_edit.iterrows():
                    status.text(f"Registrando Dpto {row['Dpto']}...")
                    post_to_google({ENTRY_DPTO: row['Dpto'], ENTRY_MONTO: row['Monto'], ENTRY_TIPO: "COBRO_MENSUAL", ENTRY_MES: mes_anio_full, ENTRY_NOTAS: "Carga Masiva"})
                    progress.progress((i + 1) / len(df_edit))
                
                status.empty()
                st.success(f"✅ Se han publicado las deudas para {mes_anio_full}.")
                time.sleep(2)
                st.rerun()

    # --- REGISTRAR PAGO (PROPIETARIO) ---
    elif not is_admin and choice == "Registrar Pago":
        st.header("📝 Mi Estado de Cuenta")
        c1, c2 = st.columns(2)
        mes_v = c1.selectbox("Mes a consultar/pagar", ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"])
        anio_v = c2.selectbox("Año", [2025, 2026, 2027], index=1)
        mes_anio_v = f"{mes_v} {anio_v}"
        
        # Leemos los datos frescos
        df_fresh = fetch_data(GID_RESPUESTAS)
        est, mon, lnk = get_latest_state(df_fresh, st.session_state.user, mes_anio_v)
        
        if est == "APROBADO":
            st.success(f"✅ ¡Todo al día! Tu pago de {mes_anio_v} por ${mon} ha sido verificado.")
            st.balloons()
        elif est == "PENDIENTE":
            st.warning(f"⏳ Pago en revisión. Ya enviaste un comprobante por ${mon} para {mes_anio_v}.")
            if st.button("Ver mi comprobante"): st.image(lnk, use_container_width=True)
        elif mon > 0:
            if est == "RECHAZADO":
                st.error("❌ Tu pago anterior fue rechazado. Por favor, sube un comprobante válido.")
            st.info(f"Monto pendiente para {mes_anio_v}: **${mon}**")
            archivo = st.file_uploader("Subir foto del voucher de pago", type=['jpg', 'png', 'jpeg'])
            if st.button("Enviar Registro de Pago"):
                if archivo:
                    with st.spinner("Subiendo comprobante..."):
                        img_res = requests.post(f"https://api.imgbb.com/1/upload?key={IMG_BB_API_KEY}", files={"image": archivo}).json()
                        img_url = img_res['data']['url']
                        if post_to_google({ENTRY_DPTO: st.session_state.user, ENTRY_MONTO: mon, ENTRY_TIPO: "PAGO_VECINO", ENTRY_MES: mes_anio_v, ENTRY_LINK: img_url}):
                            st.success("✅ Pago registrado con éxito. El administrador lo revisará pronto.")
                            time.sleep(2)
                            st.rerun()
                else: st.warning("Debe seleccionar una imagen para continuar.")
        else:
            st.warning(f"⚠️ No se encontró deuda cargada para {mes_anio_v}.")
