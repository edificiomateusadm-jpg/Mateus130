import streamlit as st
import requests
import pandas as pd
import time
from datetime import datetime
from supabase import create_client, Client

# --- CONFIGURACIÓN ---
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
IMG_BB_API_KEY = st.secrets["IMG_BB_API_KEY"]

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- CAPA DE DATOS ---
def get_user(dpto, password):
    try:
        res = supabase.table("usuarios").select("*").eq("dpto", dpto).eq("password", password).execute()
        return res.data[0] if res.data else None
    except: return None

def get_movimientos(mes_anio=None):
    try:
        query = supabase.table("movimientos").select("*")
        if mes_anio: query = query.eq("mes_anio", mes_anio)
        res = query.order("created_at").execute()
        
        # BLINDAJE: Si no hay datos, devolvemos un DataFrame con las columnas ya definidas
        if not res.data:
            return pd.DataFrame(columns=['id', 'created_at', 'dpto', 'monto', 'tipo', 'mes_anio', 'link_comprobante', 'notas'])
        
        return pd.DataFrame(res.data)
    except: 
        return pd.DataFrame(columns=['id', 'created_at', 'dpto', 'monto', 'tipo', 'mes_anio', 'link_comprobante', 'notas'])

def registrar_db(data):
    try:
        supabase.table("movimientos").insert(data).execute()
        return True
    except: return False

def get_status_logic(df_mes, dpto):
    if df_mes.empty or 'dpto' not in df_mes.columns:
        return "SIN_DEUDA", 0.0, None
    df_dpto = df_mes[df_mes['dpto'] == str(dpto)]
    if df_dpto.empty: return "SIN_DEUDA", 0.0, None
    
    monto_deuda = float(df_dpto[df_dpto['tipo'] == 'COBRO_MENSUAL']['monto'].sum())
    pagos = df_dpto[df_dpto['tipo'] == 'PAGO_VECINO']
    
    if not pagos.empty:
        ultimo_pago = pagos.iloc[-1]
        validaciones = df_dpto[(df_dpto['tipo'] == 'VALIDACION_ADMIN') & (df_dpto['created_at'] > ultimo_pago['created_at'])]
        if not validaciones.empty:
            return str(validaciones.iloc[-1]['notas']).upper(), monto_deuda, None
        return "PENDIENTE", monto_deuda, ultimo_pago['link_comprobante']
    
    return "DEUDA_EXISTENTE" if monto_deuda > 0 else "SIN_DEUDA", monto_deuda, None

# --- UI ---
st.set_page_config(page_title="Edificio Pro 2026", layout="wide")
if 'auth' not in st.session_state: st.session_state.auth = False

if not st.session_state.auth:
    st.title("🏢 Acceso")
    u = st.text_input("Unidad")
    p = st.text_input("Contraseña", type="password")
    if st.button("Entrar"):
        user_data = get_user(u, p)
        if user_data:
            st.session_state.auth, st.session_state.user, st.session_state.rol = True, u, user_data['rol']
            st.rerun()
        else: st.error("Error de acceso")

else:
    is_admin = st.session_state.rol == "ADMIN"
    menu = ["Dashboard", "Validar Pagos", "Cargar Deudas"] if is_admin else ["Dashboard", "Registrar Pago"]
    choice = st.sidebar.selectbox("Menú", menu)
    st.sidebar.button("Cerrar Sesión", on_click=lambda: st.session_state.update({"auth": False}))

    if choice == "Dashboard":
        st.title(f"👋 Panel de {st.session_state.user}")
        st.success("Conexión SQL: Activa")

    elif is_admin and choice == "Validar Pagos":
        st.header("🔍 Validación")
        df_all = get_movimientos()
        if not df_all.empty and 'mes_anio' in df_all.columns:
            for m_a in df_all['mes_anio'].unique():
                df_m = df_all[df_all['mes_anio'] == m_a]
                for d in df_m['dpto'].unique():
                    est, mon, lnk = get_status_logic(df_m, d)
                    if est == "PENDIENTE":
                        with st.expander(f"🔔 Dpto {d} - {m_a}"):
                            st.warning(f"💰 Deuda en sistema: ${mon}")
                            st.image(lnk, use_container_width=True)
                            if st.button("Aprobar", key=f"a_{d}_{m_a}"):
                                if registrar_db({"dpto": d, "monto": mon, "tipo": "VALIDACION_ADMIN", "mes_anio": m_a, "notas": "APROBADO"}): st.rerun()
                            if st.button("Rechazar", key=f"r_{d}_{m_a}"):
                                if registrar_db({"dpto": d, "monto": mon, "tipo": "VALIDACION_ADMIN", "mes_anio": m_a, "notas": "RECHAZADO"}): st.rerun()
        else:
            st.info("No hay pagos pendientes de revisión.")

    elif is_admin and choice == "Cargar Deudas":
        st.header("📈 Revisión y Carga de Deudas")
        c1, c2 = st.columns(2)
        mes = c1.selectbox("Mes", ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"])
        anio = c2.selectbox("Año", [2025, 2026, 2027], index=1)
        mes_anio_sel = f"{mes} {anio}"
        
        # Consultamos el mes (Ahora siempre traerá columnas aunque esté vacío)
        df_actual = get_movimientos(mes_anio=mes_anio_sel)
        dptos_lista = ["101","102","201","202","301","302","401","402","501","502","601","602","701","702","801"]
        
        montos_iniciales = []
        for d in dptos_lista:
            # Ahora esto no fallará porque 'dpto' y 'tipo' siempre existen
            cobro = df_actual[(df_actual['dpto'] == d) & (df_actual['tipo'] == 'COBRO_MENSUAL')]
            montos_iniciales.append(float(cobro.iloc[-1]['monto']) if not cobro.empty else 0.0)
        
        st.write(f"Editando datos para: **{mes_anio_sel}**")
        df_editor = st.data_editor(pd.DataFrame({'Dpto': dptos_lista, 'Monto': montos_iniciales}), hide_index=True, use_container_width=True, key=f"editor_{mes_anio_sel}")
        
        if st.button("🚀 Actualizar / Publicar Deudas"):
            with st.spinner("Guardando..."):
                for _, row in df_editor.iterrows():
                    # Solo guardamos si el monto es mayor a 0
                    if row['Monto'] > 0:
                        registrar_db({"dpto": row['Dpto'], "monto": row['Monto'], "tipo": "COBRO_MENSUAL", "mes_anio": mes_anio_sel, "notas": "Carga"})
                st.success(f"Datos de {mes_anio_sel} actualizados.")
                time.sleep(1)
                st.rerun()

    elif not is_admin and choice == "Registrar Pago":
        st.header("📝 Mi Estado")
        df_t = get_movimientos()
        if not df_t.empty and 'mes_anio' in df_t.columns:
            m_disp = sorted(df_t['mes_anio'].unique())
            m_sel = st.selectbox("Periodo", m_disp)
            est, mon, lnk = get_status_logic(df_t[df_t['mes_anio'] == m_sel], st.session_state.user)
            if est == "APROBADO": st.success(f"✅ {m_sel}: ${mon} APROBADO")
            elif est == "PENDIENTE": st.warning("⏳ En revisión")
            elif mon > 0:
                st.info(f"Deuda: ${mon}")
                foto = st.file_uploader("Voucher", type=['jpg', 'png', 'jpeg'])
                if st.button("Enviar") and foto:
                    res_img = requests.post(f"https://api.imgbb.com/1/upload?key={IMG_BB_API_KEY}", files={"image": foto}).json()
                    registrar_db({"dpto": st.session_state.user, "monto": mon, "tipo": "PAGO_VECINO", "mes_anio": m_sel, "link_comprobante": res_img['data']['url']})
                    st.rerun()
        else: st.warning("No hay deudas cargadas.")
