import streamlit as st
from st_supabase_connection import SupabaseConnection, execute_query
import pandas as pd
from datetime import datetime

# --- CONFIGURACIÓN ---
# Estos datos los sacas de Project Settings > API en tu panel de Supabase
SUPABASE_URL = "TU_URL_DE_SUPABASE"
SUPABASE_KEY = "TU_ANON_KEY_DE_SUPABASE"

st.set_page_config(page_title="Edificio Pro SQL", layout="wide")

# Conexión
conn = st.connection("supabase", type=SupabaseConnection, url=SUPABASE_URL, key=SUPABASE_KEY)

# --- CAPA DE DATOS ---
def login_user(u, p):
    res = execute_query(conn.table("usuarios").select("*").eq("dpto", u).eq("password", p))
    return res.data[0] if res.data else None

def registrar_movimiento(dpto, monto, tipo, mes_anio, link="", notas=""):
    data = {
        "dpto": str(dpto),
        "monto": float(monto),
        "tipo": tipo,
        "mes_anio": mes_anio,
        "link_comprobante": link,
        "notas": notas
    }
    execute_query(conn.table("movimientos").insert(data))

def obtener_estado(dpto, mes_anio):
    # Traemos todos los movimientos de ese dpto y mes
    res = execute_query(conn.table("movimientos").select("*").eq("dpto", dpto).eq("mes_anio", mes_anio).order("timestamp"))
    df = pd.DataFrame(res.data)
    
    if df.empty: return "SIN_DEUDA", 0, None
    
    monto_deuda = df[df['tipo'] == 'COBRO_MENSUAL']['monto'].sum()
    pagos = df[df['tipo'] == 'PAGO_VECINO']
    
    if not pagos.empty:
        ultimo_pago = pagos.iloc[-1]
        validaciones = df[(df['tipo'] == 'VALIDACION_ADMIN') & (df['timestamp'] > ultimo_pago['timestamp'])]
        
        if not validaciones.empty:
            return validaciones.iloc[-1]['notas'], monto_deuda, None
        return "PENDIENTE", monto_deuda, ultimo_pago['link_comprobante']
    
    return "DEUDA_EXISTENTE" if monto_deuda > 0 else "SIN_DEUDA", monto_deuda, None

# --- LÓGICA DE INTERFAZ ---
if 'auth' not in st.session_state: st.session_state.auth = False

if not st.session_state.auth:
    st.title("🏢 Acceso Seguro (SQL)")
    u = st.text_input("Unidad")
    p = st.text_input("Contraseña", type="password")
    if st.button("Entrar"):
        user_data = login_user(u, p)
        if user_data:
            st.session_state.auth = True
            st.session_state.user = u
            st.session_state.rol = user_data['rol']
            st.rerun()
        else:
            st.error("Credenciales inválidas")

else:
    is_admin = st.session_state.rol == "ADMIN"
    # El resto de tu lógica de Dashboard, Validar y Cargar es casi idéntica
    # Solo que ahora usas registrar_movimiento() en lugar de post_to_google()
    st.sidebar.write(f"Usuario: {st.session_state.user}")
    if st.sidebar.button("Salir"):
        st.session_state.auth = False
        st.rerun()
    
    # Ejemplo rápido de Carga para Admin:
    if is_admin:
        st.subheader("Cargar Deuda")
        m = st.selectbox("Mes", ["Enero", "Febrero"])
        mon = st.number_input("Monto", value=100)
        if st.button("Asignar a todos"):
            dptos = ["101", "102", "201"] # Esto lo puedes traer de la tabla usuarios
            for d in dptos:
                registrar_movimiento(d, mon, 'COBRO_MENSUAL', f"{m} 2026")
            st.success("Cargado en DB")
