import streamlit as st
import requests
import pandas as pd
from datetime import datetime
from supabase import create_client, Client

# --- CONFIGURACIÓN ---
# Reemplaza con tus datos de Supabase
SUPABASE_URL = "TU_URL_DE_SUPABASE"
SUPABASE_KEY = "TU_ANON_KEY_DE_SUPABASE"
IMG_BB_API_KEY = "4d082bcad64d3390228ec3d92cdc15c3"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- CAPA DE DATOS ---
def get_user(dpto, password):
    res = supabase.table("usuarios").select("*").eq("dpto", dpto).eq("password", password).execute()
    return res.data[0] if res.data else None

def get_movimientos(dpto=None, mes_anio=None):
    query = supabase.table("movimientos").select("*")
    if dpto: query = query.eq("dpto", dpto)
    if mes_anio: query = query.eq("mes_anio", mes_anio)
    res = query.order("created_at").execute()
    return pd.DataFrame(res.data)

def registrar_db(data):
    supabase.table("movimientos").insert(data).execute()

def get_status_logic(df_mes, dpto):
    # Lógica para determinar el estado actual de un dpto en un mes
    df_dpto = df_mes[df_mes['dpto'] == dpto]
    if df_dpto.empty: return "SIN_DEUDA", 0.0, None
    
    monto_deuda = float(df_dpto[df_dpto['tipo'] == 'COBRO_MENSUAL']['monto'].sum())
    pagos = df_dpto[df_dpto['tipo'] == 'PAGO_VECINO']
    
    if not pagos.empty:
        ultimo_pago = pagos.iloc[-1]
        validaciones = df_dpto[(df_dpto['tipo'] == 'VALIDACION_ADMIN') & 
                               (df_dpto['created_at'] > ultimo_pago['created_at'])]
        
        if not validaciones.empty:
            return validaciones.iloc[-1]['notas'].upper(), monto_deuda, None
        return "PENDIENTE", monto_deuda, ultimo_pago['link_comprobante']
    
    return "DEUDA_EXISTENTE" if monto_deuda > 0 else "SIN_DEUDA", monto_deuda, None

# --- INTERFAZ ---
st.set_page_config(page_title="Edificio Pro SQL", layout="wide")

if 'auth' not in st.session_state: st.session_state.auth = False

if not st.session_state.auth:
    st.title("🏢 Sistema Edificio (SQL Mode)")
    u = st.text_input("Unidad / Dpto")
    p = st.text_input("Contraseña", type="password")
    if st.button("Ingresar"):
        user_data = get_user(u, p)
        if user_data:
            st.session_state.auth, st.session_state.user = True, u
            st.session_state.rol = user_data['rol']
            st.rerun()
        else: st.error("Usuario o clave incorrectos")

else:
    is_admin = st.session_state.rol == "ADMIN"
    menu = ["Dashboard", "Validar Pagos", "Cargar Deudas"] if is_admin else ["Dashboard", "Registrar Pago"]
    choice = st.sidebar.selectbox("Menú", menu)
    st.sidebar.button("Cerrar Sesión", on_click=lambda: st.session_state.update({"auth": False}))

    # --- DASHBOARD ---
    if choice == "Dashboard":
        st.title(f"👋 Panel de {st.session_state.user}")
        st.write(f"Conexión a Base de Datos: **Activa ✅**")
        st.info("Utiliza el menú lateral para operar.")

    # --- VALIDAR (ADMIN) ---
    elif is_admin and choice == "Validar Pagos":
        st.header("🔍 Pagos por Validar")
        df = get_movimientos()
        if not df.empty:
            # Buscamos dptos con pagos pendientes
            for mes_anio in df['mes_anio'].unique():
                df_mes = df[df['mes_anio'] == mes_anio]
                for d in df_mes['dpto'].unique():
                    est, mon, lnk = get_status_logic(df_mes, d)
                    if est == "PENDIENTE":
                        with st.expander(f"Dpto {d} - {mes_anio} (${mon})"):
                            st.image(lnk, width=300)
                            c1, c2 = st.columns(2)
                            if c1.button("Aprobar", key=f"ap_{d}_{mes_anio}"):
                                registrar_db({"dpto": d, "monto": mon, "tipo": "VALIDACION_ADMIN", "mes_anio": mes_anio, "notas": "APROBADO"})
                                st.rerun()
                            if c2.button("Rechazar", key=f"re_{d}_{mes_anio}"):
                                registrar_db({"dpto": d, "monto": mon, "tipo": "VALIDACION_ADMIN", "mes_anio": mes_anio, "notas": "RECHAZADO"})
                                st.rerun()

    # --- CARGAR DEUDAS (ADMIN) ---
    elif is_admin and choice == "Cargar Deudas":
        st.header("📈 Publicar Deudas")
        m = st.selectbox("Mes", ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"])
        a = st.selectbox("Año", [2025, 2026, 2027])
        mes_anio = f"{m} {a}"
        
        # Lista de dptos (puedes traerla de la tabla usuarios)
        dptos = ["101","102","201","202","301","302","401","402","501","502","601","602","701","702","801"]
        df_edit = st.data_editor(pd.DataFrame({'Dpto': dptos, 'Monto': [0.0]*len(dptos)}), hide_index=True)
        
        if st.button("Guardar en Base de Datos"):
            for _, r in df_edit.iterrows():
                if r['Monto'] > 0:
                    registrar_db({"dpto": r['Dpto'], "monto": r['Monto'], "tipo": "COBRO_MENSUAL", "mes_anio": mes_anio})
            st.success("✅ Deudas publicadas instantáneamente.")

    # --- REGISTRAR PAGO (VECINO) ---
    elif not is_admin and choice == "Registrar Pago":
        st.header("📝 Mi Estado")
        m_v = st.selectbox("Mes", ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"])
        a_v = st.selectbox("Año", [2025, 2026, 2027], index=1)
        mes_anio_v = f"{m_v} {a_v}"
        
        df_res = get_movimientos(mes_anio=mes_anio_v)
        est, mon, lnk = get_status_logic(df_res, st.session_state.user)
        
        if est == "APROBADO": st.success(f"✅ Pago de {mes_anio_v} por ${mon} APROBADO.")
        elif est == "PENDIENTE": st.warning(f"⏳ Pago enviado. En revisión.")
        elif mon > 0:
            st.info(f"Deuda pendiente: ${mon}")
            foto = st.file_uploader("Subir comprobante", type=['jpg', 'png', 'jpeg'])
            if st.button("Enviar Pago") and foto:
                # Subir a ImgBB
                res_img = requests.post(f"https://api.imgbb.com/1/upload?key={IMG_BB_API_KEY}", files={"image": foto}).json()
                registrar_db({"dpto": st.session_state.user, "monto": mon, "tipo": "PAGO_VECINO", "mes_anio": mes_anio_v, "link_comprobante": res_img['data']['url']})
                st.rerun()
        else: st.warning("No hay deuda cargada para este mes.")
