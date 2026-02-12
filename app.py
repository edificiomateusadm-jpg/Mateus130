import streamlit as st
import requests
import base64
import pandas as pd
from datetime import datetime

# --- CONFIGURACIÓN DE CREDENCIALES ---
IMG_BB_API_KEY = "4d082bcad64d3390228ec3d92cdc15c3"
FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLScsT1z4dK51DHmbH797A8KEDZP7s4R6FX_xmVTBCew2vGIbQA/formResponse"

# URLs de Google Sheets (Formato Exportación CSV)
SHEET_USUARIOS_URL = "https://docs.google.com/spreadsheets/d/1FvnEi2HI4xjJg7IwYmhxPQESV8OaQrOZEfxmCXwSUx4/export?format=csv&gid=284650027"
SHEET_DEUDAS_URL = "https://docs.google.com/spreadsheets/d/1FvnEi2HI4xjJg7IwYmhxPQESV8OaQrOZEfxmCXwSUx4/export?format=csv&gid=2119767041"

# IDs de Google Form (Mantenemos los que me pasaste)
ENTRY_DPTO = "entry.496848869"
ENTRY_MONTO = "entry.1553105788"
ENTRY_TIPO = "entry.1626552330"
ENTRY_MES = "entry.550569407"
ENTRY_LINK = "entry.791154903"
ENTRY_NOTAS = "entry.2019103542"

# --- FUNCIONES AUXILIARES ---
def obtener_usuarios():
    try:
        df = pd.read_csv(SHEET_USUARIOS_URL)
        return dict(zip(df['Dpto'].astype(str), df['Password'].astype(str)))
    except:
        return {}

def obtener_deuda_especifica(dpto, mes, anio):
    try:
        # Leemos la pestaña de deudas directamente
        df_deudas = pd.read_csv(SHEET_DEUDAS_URL)
        # Filtramos por dpto y el string del mes/año que genera el formulario
        mes_anio_buscado = f"{mes} {anio}"
        fila = df_deudas[(df_deudas['Dpto'].astype(str) == str(dpto)) & 
                          (df_deudas['Mes'].astype(str) == mes_anio_buscado)]
        if not fila.empty:
            return float(fila['Monto'].values[-1]) # Tomamos el registro más reciente
        return 0.0
    except:
        return 0.0

def subir_a_imgbb(file):
    url = "https://api.imgbb.com/1/upload"
    img_data = base64.b64encode(file.read()).decode('utf-8')
    payload = {"key": IMG_BB_API_KEY, "image": img_data}
    res = requests.post(url, data=payload)
    return res.json()['data']['url'] if res.status_code == 200 else None

def enviar_a_google_form(datos):
    res = requests.post(FORM_URL, data=datos)
    return res.status_code == 200

# --- INTERFAZ ---
st.set_page_config(page_title="Gestión Edificio 2026", page_icon="🏢", layout="wide")

if 'autenticado' not in st.session_state:
    st.session_state.autenticado = False

# --- PANTALLA DE LOGIN ---
if not st.session_state.autenticado:
    st.title("🏢 Sistema de Administración de Edificio")
    with st.container():
        usuarios_db = obtener_usuarios()
        if usuarios_db:
            user = st.selectbox("Seleccione su Departamento / Rol", list(usuarios_db.keys()))
            pwd = st.text_input("Contraseña", type="password")
            if st.button("Ingresar"):
                if pwd == usuarios_db.get(user):
                    st.session_state.autenticado = True
                    st.session_state.user = user
                    st.rerun()
                else:
                    st.error("❌ Credenciales incorrectas.")
        else:
            st.error("Error cargando base de usuarios. Verifique conexión.")

# --- APP AUTENTICADA ---
else:
    st.sidebar.header(f"Sesión: {st.session_state.user}")
    
    # Definición de Menús según el ROL
    es_admin = st.session_state.user in ["ADMIN", "ADMINISTRADOR", "Admin"]
    
    if es_admin:
        menu = ["Resumen General", "Cargar Deudas del Mes", "Registrar Gasto Edificio"]
    else:
        menu = ["Mi Estado", "Registrar Pago de Cuota"]
    
    opcion = st.sidebar.selectbox("Menú Principal", menu)

    # --- LÓGICA ADMINISTRADOR ---
    if es_admin:
        if opcion == "Cargar Deudas del Mes":
            st.header("💰 Carga Mensual de Consumos")
            st.write("Complete los montos (Cuota Fija + Consumo de Agua) para cada unidad.")
            
            c1, c2 = st.columns(2)
            mes_sel = c1.selectbox("Mes", ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"])
            anio_sel = c2.number_input("Año", min_value=2024, max_value=2030, value=2026)
            
            dptos_lista = ["101", "102", "201", "202", "301", "302", "401", "402", "501", "502", "601", "602", "701", "702", "801"]
            df_carga = pd.DataFrame({'Dpto': dptos_lista, 'Monto': [0.0]*15})
            
            st.info("💡 Edite los valores directamente en la tabla y presione el botón de abajo.")
            tabla_editada = st.data_editor(df_carga, hide_index=True, use_container_width=True)

            if st.button("Publicar Deudas del Mes"):
                with st.spinner("Procesando envíos..."):
                    error_count = 0
                    for _, row in tabla_editada.iterrows():
                        payload = {
                            ENTRY_DPTO: row['Dpto'],
                            ENTRY_MONTO: row['Monto'],
                            ENTRY_TIPO: "COBRO_MENSUAL",
                            ENTRY_MES: f"{mes_sel} {anio_sel}",
                            ENTRY_LINK: "N/A",
                            ENTRY_NOTAS: "Carga masiva ADMIN"
                        }
                        if not enviar_a_google_form(payload): error_count += 1
                    
                    if error_count == 0:
                        st.success(f"✅ Deudas de {mes_sel} {anio_sel} publicadas con éxito.")
                    else:
                        st.warning(f"Se enviaron registros, pero hubo {error_count} errores.")

        elif opcion == "Registrar Gasto Edificio":
            st.header("💸 Registro de Gastos (Egresos)")
            with st.form("form_gastos", clear_on_submit=True):
                concepto = st.text_input("Concepto (Ej: Pago Luz Pasillos, Reparación Ascensor)")
                monto_gasto = st.number_input("Monto Total", min_value=0.0)
                mes_gasto = st.selectbox("Mes de ejecución", ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"])
                anio_gasto = st.number_input("Año", value=2026)
                factura = st.file_uploader("Subir Factura/Recibo", type=['jpg','png','pdf'])
                
                if st.form_submit_button("Registrar Gasto"):
                    if factura:
                        url_img = subir_a_imgbb(factura)
                        payload = {
                            ENTRY_DPTO: "ADMIN",
                            ENTRY_MONTO: monto_gasto,
                            ENTRY_TIPO: "GASTO_ADMIN",
                            ENTRY_MES: f"{mes_gasto} {anio_gasto}",
                            ENTRY_LINK: url_img,
                            ENTRY_NOTAS: concepto
                        }
                        if enviar_a_google_form(payload): st.success("Gasto registrado y visible para propietarios.")
                    else: st.error("Es obligatorio subir evidencia del gasto.")

    # --- LÓGICA PROPIETARIO ---
    else:
        if opcion == "Registrar Pago de Cuota":
            st.header("📝 Registrar mi Pago")
            
            c1, c2 = st.columns(2)
            mes_p = c1.selectbox("Mes a Pagar", ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"])
            anio_p = c2.number_input("Año", min_value=2024, max_value=2030, value=2026)
            
            monto_deuda = obtener_deuda_especifica(st.session_state.user, mes_p, anio_p)
            
            if monto_deuda > 0:
                st.warning(f"🔔 Monto a pagar para {mes_p} {anio_p}: **${monto_deuda}**")
            else:
                st.info("ℹ️ El administrador aún no ha cargado el monto de este mes.")

            with st.form("form_pago", clear_on_submit=True):
                monto_confirmado = st.number_input("Monto que está pagando", value=float(monto_deuda))
                comprobante = st.file_uploader("Seleccionar Comprobante (Cámara/Galería)", type=['jpg','png','jpeg'])
                nota_pago = st.text_area("Comentario opcional")
                
                if st.form_submit_button("Enviar Comprobante"):
                    if comprobante and monto_confirmado > 0:
                        with st.spinner("Subiendo evidencia..."):
                            url_pago = subir_a_imgbb(comprobante)
                            if url_pago:
                                payload = {
                                    ENTRY_DPTO: st.session_state.user,
                                    ENTRY_MONTO: monto_confirmado,
                                    ENTRY_TIPO: "PAGO_VECINO",
                                    ENTRY_MES: f"{mes_p} {anio_p}",
                                    ENTRY_LINK: url_pago,
                                    ENTRY_NOTAS: nota_pago
                                }
                                if enviar_a_google_form(payload):
                                    st.success("✅ Pago enviado. El administrador lo validará pronto.")
                            else: st.error("Error al procesar la imagen.")
                    else: st.warning("Asegúrese de subir la foto y que el monto sea mayor a 0.")

    if st.sidebar.button("Cerrar Sesión"):
        st.session_state.autenticado = False
        st.rerun()
