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
        if not res.data:
            return pd.DataFrame(columns=['id', 'created_at', 'dpto', 'monto', 'tipo', 'mes_anio', 'link_comprobante', 'notas'])
        return pd.DataFrame(res.data)
    except: return pd.DataFrame(columns=['id', 'created_at', 'dpto', 'monto', 'tipo', 'mes_anio', 'link_comprobante', 'notas'])

def get_gastos():
    try:
        res = supabase.table("gastos").select("*").order("fecha_gasto", desc=True).execute()
        return pd.DataFrame(res.data) if res.data else pd.DataFrame()
    except: return pd.DataFrame()

def registrar_db(tabla, data):
    try:
        supabase.table(tabla).insert(data).execute()
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
st.set_page_config(page_title="Gestión Edificio 2026", layout="wide")
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
    menu = ["Dashboard", "Validar Pagos", "Cargar Deudas", "Registrar Gastos"] if is_admin else ["Dashboard", "Registrar Pago", "Ver Gastos"]
    choice = st.sidebar.selectbox("Menú", menu)
    st.sidebar.button("Cerrar Sesión", on_click=lambda: st.session_state.update({"auth": False}))

    # 1. DASHBOARD
    if choice == "Dashboard":
        st.title(f"👋 Hola, {st.session_state.user}")
        df_p = get_movimientos()
        df_g = get_gastos()
        ingresos = df_p[df_p['tipo'] == 'VALIDACION_ADMIN']['monto'].sum() if not df_p.empty else 0
        egresos = df_g['monto'].sum() if not df_g.empty else 0
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Ingresos Totales", f"S/ {ingresos:,.2f}")
        c2.metric("Egresos Totales", f"S/ {egresos:,.2f}")
        c3.metric("Caja Actual", f"S/ {ingresos - egresos:,.2f}")
        
        st.divider()
        st.info("Utiliza el menú lateral para gestionar pagos o revisar cuentas.")

    # 2. VALIDAR PAGOS (ADMIN)
    elif is_admin and choice == "Validar Pagos":
        st.header("🔍 Validación de Comprobantes")
        df_all = get_movimientos()
        if not df_all.empty:
            pendientes = False
            for m_a in df_all['mes_anio'].unique():
                df_m = df_all[df_all['mes_anio'] == m_a]
                for d in df_m['dpto'].unique():
                    est, mon, lnk = get_status_logic(df_m, d)
                    if est == "PENDIENTE":
                        pendientes = True
                        with st.expander(f"Dpto {d} - {m_a}"):
                            st.write(f"Monto esperado: **S/ {mon}**")
                            st.image(lnk, use_container_width=True)
                            col1, col2 = st.columns(2)
                            if col1.button("✅ Aprobar", key=f"ap_{d}_{m_a}"):
                                registrar_db("movimientos", {"dpto": d, "monto": mon, "tipo": "VALIDACION_ADMIN", "mes_anio": m_a, "notas": "APROBADO"})
                                st.rerun()
                            if col2.button("❌ Rechazar", key=f"re_{d}_{m_a}"):
                                registrar_db("movimientos", {"dpto": d, "monto": mon, "tipo": "VALIDACION_ADMIN", "mes_anio": m_a, "notas": "RECHAZADO"})
                                st.rerun()
            if not pendientes: st.success("Todo al día.")

    # 3. CARGAR DEUDAS (ADMIN)
    elif is_admin and choice == "Cargar Deudas":
        st.header("📈 Cargar Cuotas")
        c1, c2 = st.columns(2)
        mes = c1.selectbox("Mes", ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"])
        anio = c2.selectbox("Año", [2025, 2026, 2027], index=1)
        mes_anio_sel = f"{mes} {anio}"
        df_actual = get_movimientos(mes_anio=mes_anio_sel)
        dptos_lista = ["101","102","201","202","301","302","401","402","501","502","601","602","701","702","801"]
        montos_ini = []
        for d in dptos_lista:
            cobro = df_actual[(df_actual['dpto'] == d) & (df_actual['tipo'] == 'COBRO_MENSUAL')]
            montos_ini.append(float(cobro.iloc[-1]['monto']) if not cobro.empty else 0.0)
        df_ed = st.data_editor(pd.DataFrame({'Dpto': dptos_lista, 'Monto': montos_ini}), hide_index=True, key=f"ed_{mes_anio_sel}")
        if st.button("Guardar"):
            for _, r in df_ed.iterrows():
                if r['Monto'] > 0: registrar_db("movimientos", {"dpto": r['Dpto'], "monto": r['Monto'], "tipo": "COBRO_MENSUAL", "mes_anio": mes_anio_sel, "notas": "Carga"})
            st.rerun()

    # 4. REGISTRAR GASTOS (ADMIN)
    elif is_admin and choice == "Registrar Gastos":
        st.header("💸 Registrar Gasto")
        with st.form("g"):
            f = st.date_input("Fecha")
            c = st.selectbox("Categoría", ["Luz", "Agua", "Mantenimiento", "Limpieza", "Otros"])
            d = st.text_input("Descripción")
            m = st.number_input("Monto S/", min_value=0.0)
            img = st.file_uploader("Recibo", type=['jpg','png','jpeg'])
            if st.form_submit_button("Guardar Gasto") and img and d:
                r = requests.post(f"https://api.imgbb.com/1/upload?key={IMG_BB_API_KEY}", files={"image": img}).json()
                registrar_db("gastos", {"fecha_gasto": str(f), "categoria": c, "descripcion": d, "monto": m, "link_factura": r['data']['url']})
                st.success("Gasto guardado"); st.rerun()

    # 5. REGISTRAR PAGO (VECINO)
    elif not is_admin and choice == "Registrar Pago":
        st.header("📝 Mis Pagos")
        df_t = get_movimientos()
        if not df_t.empty:
            m_disp = sorted(df_t['mes_anio'].unique())
            m_sel = st.selectbox("Periodo", m_disp)
            est, mon, lnk = get_status_logic(df_t[df_t['mes_anio'] == m_sel], st.session_state.user)
            if est == "APROBADO": st.success(f"✅ Pagado S/ {mon}")
            elif est == "PENDIENTE": st.warning("⏳ En revisión")
            elif mon > 0:
                st.info(f"Deuda: S/ {mon}")
                f_p = st.file_uploader("Subir Voucher", type=['jpg','png','jpeg'])
                if st.button("Enviar Pago") and f_p:
                    r_i = requests.post(f"https://api.imgbb.com/1/upload?key={IMG_BB_API_KEY}", files={"image": f_p}).json()
                    registrar_db("movimientos", {"dpto": st.session_state.user, "monto": mon, "tipo": "PAGO_VECINO", "mes_anio": m_sel, "link_comprobante": r_i['data']['url']})
                    st.rerun()
        else: st.info("No hay deudas cargadas.")

    # 6. VER GASTOS (VECINO) - NUEVA SECCIÓN
    elif not is_admin and choice == "Ver Gastos":
        st.header("📊 Gastos del Edificio")
        st.write("Lista cronológica de gastos realizados por la administración.")
        df_g = get_gastos()
        if not df_g.empty:
            # Mostramos una tabla amigable
            for i, row in df_g.iterrows():
                with st.container(border=True):
                    col1, col2, col3 = st.columns([1, 2, 1])
                    col1.write(f"📅 **{row['fecha_gasto']}**")
                    col2.write(f"📌 **{row['categoria']}**: {row['descripcion']}")
                    col3.write(f"💰 **S/ {row['monto']:,.2f}**")
                    if st.button("Ver Comprobante", key=f"btn_g_{row['id']}"):
                        st.image(row['link_factura'], caption=f"Recibo - {row['descripcion']}", use_container_width=True)
        else:
            st.info("No hay gastos registrados todavía.")
