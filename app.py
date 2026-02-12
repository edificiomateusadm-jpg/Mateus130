import streamlit as st
import requests
import base64
import pandas as pd

# --- CONFIGURACIÓN DE CREDENCIALES ---
IMG_BB_API_KEY = "4d082bcad64d3390228ec3d92cdc15c3"
FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLScsT1z4dK51DHmbH797A8KEDZP7s4R6FX_xmVTBCew2vGIbQA/formResponse"

# URL de la pestaña de Usuarios (formato exportación CSV)
SHEET_USUARIOS_URL = "https://docs.google.com/spreadsheets/d/1FvnEi2HI4xjJg7IwYmhxPQESV8OaQrOZEfxmCXwSUx4/export?format=csv&gid=284650027"

# IDs de Google Form
ENTRY_DPTO = "entry.496848869"
ENTRY_MONTO = "entry.1553105788"
ENTRY_TIPO = "entry.1626552330"
ENTRY_MES = "entry.550569407"
ENTRY_LINK = "entry.791154903"
ENTRY_NOTAS = "entry.2019103542"

# --- FUNCIONES CORE ---
def obtener_usuarios():
    try:
        df = pd.read_csv(SHEET_USUARIOS_URL)
        # Convertimos a diccionario {Dpto: Password}
        return dict(zip(df['Dpto'].astype(str), df['Password'].astype(str)))
    except Exception as e:
        st.error(f"Error al cargar base de datos de usuarios: {e}")
        return {}

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
    usuarios_db = obtener_usuarios()
    
    if usuarios_db:
        dptos_lista = list(usuarios_db.keys())
        user = st.selectbox("Seleccione su unidad", dptos_lista)
        pwd = st.text_input("Contraseña", type="password")
        
        if st.button("Ingresar"):
            if pwd == usuarios_db.get(user):
                st.session_state.autenticado = True
                st.session_state.user = user
                st.rerun()
            else:
                st.error("❌ Contraseña incorrecta")
    else:
        st.warning("Cargando lista de usuarios...")

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
        st.info("Visualización de ingresos y egresos (Próximamente Fase 2)")
        
    elif choice == "Registrar Pago/Gasto":
        tipo = "PAGO_VECINO" if st.session_state.user not in ["ADMIN", "ADMINISTRADOR"] else "GASTO_ADMIN"
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
                            st.error("❌ Error al conectar con el formulario.")
                    else:
                        st.error("❌ Error al subir la imagen a ImgBB.")
                else:
                    st.warning("Por favor sube una foto del comprobante.")
