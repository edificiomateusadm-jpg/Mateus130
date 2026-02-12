import streamlit as st
import requests
import base64
import pandas as pd

# --- CONFIGURACIÓN DE CRÉDENCIALES ---
IMG_BB_API_KEY = "4d082bcad64d3390228ec3d92cdc15c3"
FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLScsT1z4dK51DHmbH797A8KEDZP7s4R6FX_xmVTBCew2vGIbQA/formResponse"

# IDs de Google Form
ENTRY_DPTO = "entry.496848869"
ENTRY_MONTO = "entry.1553105788"
ENTRY_TIPO = "entry.1626552330"
ENTRY_MES = "entry.550569407"
ENTRY_LINK = "entry.791154903"
ENTRY_NOTAS = "entry.2019103542"

# --- FUNCIONES CORE ---
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
st.set_page_config(page_title="Administración Edificio", page_icon="🏢")

if 'autenticado' not in st.session_state:
    st.session_state.autenticado = False

# --- LOGIN ---
if not st.session_state.autenticado:
    st.header("🏢 Acceso al Edificio")
    dptos_lista = ["101", "102", "201", "202", "301", "302", "401", "402", "501", "502", "601", "602", "701", "702", "801", "ADMIN"]
    user = st.selectbox("Seleccione su unidad", dptos_lista)
    pwd = st.text_input("Contraseña", type="password")
    
    if st.button("Ingresar"):
        # Lógica simple: si es admin usa una clave fija, si es dpto usa otra.
        # En el futuro, aquí leerás tu pestaña 'Usuarios' de Google Sheets.
        if (user == "ADMIN" and pwd == "admin123") or (pwd == f"clave{user}"):
            st.session_state.autenticado = True
            st.session_state.user = user
            st.rerun()
        else:
            st.error("Contraseña incorrecta")

# --- DASHBOARD PRINCIPAL ---
else:
    st.sidebar.title(f"Unidad: {st.session_state.user}")
    if st.sidebar.button("Cerrar Sesión"):
        st.session_state.autenticado = False
        st.rerun()

    menu = ["Dashboard", "Registrar Pago/Gasto"]
    choice = st.sidebar.selectbox("Menú", menu)

    if choice == "Dashboard":
        st.title("📊 Estado Financiero")
        st.info("Aquí se mostrarán los datos de tu Google Sheet en la Fase 2.")
        # Aquí puedes usar pd.read_csv para mostrar la tabla de pagos realizados.

    elif choice == "Registrar Pago/Gasto":
        tipo = "PAGO_VECINO" if st.session_state.user != "ADMIN" else "GASTO_ADMIN"
        st.subheader(f"Cargar {tipo.replace('_', ' ')}")
        
        with st.form("registro_form", clear_on_submit=True):
            monto = st.number_input("Monto", min_value=0.0)
            mes = st.selectbox("Mes correspondiente", ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"])
            archivo = st.file_uploader("Comprobante (Cámara o Galería)", type=['jpg', 'png', 'jpeg'])
            notas = st.text_area("Notas adicionales")
            
            enviar = st.form_submit_button("Subir Registro")
            
            if enviar:
                if archivo:
                    with st.spinner("Subiendo imagen..."):
                        link_foto = subir_a_imgbb(archivo)
                    
                    if link_foto:
                        payload = {
                            ENTRY_DPTO: st.session_state.user,
                            ENTRY_MONTO: monto,
                            ENTRY_TIPO: tipo,
                            ENTRY_MES: mes,
                            ENTRY_LINK: link_foto,
                            ENTRY_NOTAS: notas
                        }
                        if enviar_a_google_form(payload):
                            st.success("✅ Registro enviado correctamente.")
                        else:
                            st.error("❌ Error al conectar con la base de datos.")
                    else:
                        st.error("❌ Error al subir la imagen a ImgBB.")
                else:
                    st.warning("Por favor sube una foto del comprobante.")