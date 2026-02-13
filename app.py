import streamlit as st
import requests
import pandas as pd
import time
import plotly.express as px
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
        df = pd.DataFrame(res.data)
        df['created_at'] = pd.to_datetime(df['created_at'], errors='coerce')
        return df
    except: return pd.DataFrame()

def get_gastos():
    try:
        res = supabase.table("gastos").select("*").order("fecha_gasto", desc=False).execute()
        if not res.data: 
            return pd.DataFrame(columns=['id', 'created_at', 'fecha_gasto', 'categoria', 'descripcion', 'monto', 'link_factura'])
        df = pd.DataFrame(res.data)
        df['fecha_gasto'] = pd.to_datetime(df['fecha_gasto'], errors='coerce')
        return df
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
    st.title("🏢 Acceso al Edificio")
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

    # 1. DASHBOARD GRÁFICO
    if choice == "Dashboard":
        st.title(f"📊 Dashboard Financiero - {st.session_state.user}")
        
        df_mov = get_movimientos()
        df_gas = get_gastos()
        
        # Procesar Ingresos Aprobados
        ing_df = df_mov[df_mov['tipo'] == 'VALIDACION_ADMIN'].copy()
        ing_df = ing_df.rename(columns={'created_at': 'Fecha', 'monto': 'Monto'})
        ing_df['Clase'] = 'Ingreso'
        
        # Procesar Gastos
        gas_df = df_gas.copy()
        gas_df = gas_df.rename(columns={'fecha_gasto': 'Fecha', 'monto': 'Monto'})
        gas_df['Clase'] = 'Gasto'
        
        # Unificar y forzar formato fecha
        df_final = pd.concat([ing_df[['Fecha', 'Monto', 'Clase']], gas_df[['Fecha', 'Monto', 'Clase', 'categoria'] if 'categoria' in gas_df.columns else ['Fecha', 'Monto', 'Clase']]])
        df_final['Fecha'] = pd.to_datetime(df_final['Fecha'], errors='coerce')
        df_final = df_final.dropna(subset=['Fecha']) # Limpiar filas sin fecha

        # Métricas
        total_in = float(ing_df['Monto'].sum()) if not ing_df.empty else 0.0
        total_out = float(gas_df['Monto'].sum()) if not gas_df.empty else 0.0
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Ingresos Aprobados", f"S/ {total_in:,.2f}")
        c2.metric("Gastos Totales", f"S/ {total_out:,.2f}")
        c3.metric("Caja Disponible", f"S/ {total_in - total_out:,.2f}")

        st.divider()

        if not df_final.empty:
            col_graph1, col_graph2 = st.columns([2, 1])
            
            with col_graph1:
                st.subheader("Evolución de Fondos")
                # Agrupamos por fecha (día) y clase
                df_plot = df_final.groupby([df_final['Fecha'].dt.date, 'Clase'])['Monto'].sum().reset_index()
                fig_line = px.line(df_plot, x='Fecha', y='Monto', color='Clase', 
                                  markers=True, color_discrete_map={'Ingreso': '#00CC96', 'Gasto': '#EF553B'})
                st.plotly_chart(fig_line, use_container_width=True)

            with col_graph2:
                st.subheader("Gastos por Categoría")
                if not gas_df.empty:
                    fig_pie = px.pie(gas_df, values='Monto', names='categoria', hole=0.4,
                                    color_discrete_sequence=px.colors.qualitative.Pastel)
                    st.plotly_chart(fig_pie, use_container_width=True)
                else:
                    st.info("No hay gastos registrados.")
            
            
        else:
            st.info("Aún no hay datos para generar gráficos.")

    # (El resto de las secciones permanecen igual pero con los nombres de tabla correctos)
    elif is_admin and choice == "Validar Pagos":
        st.header("🔍 Validación")
        df_all = get_movimientos()
        pendientes = False
        if not df_all.empty:
            for m_a in df_all['mes_anio'].unique():
                df_m = df_all[df_all['mes_anio'] == m_a]
                for d in df_m['dpto'].unique():
                    est, mon, lnk = get_status_logic(df_m, d)
                    if est == "PENDIENTE":
                        pendientes = True
                        with st.expander(f"Dpto {d} - {m_a}"):
                            st.warning(f"💰 Deuda: S/ {mon}")
                            st.image(lnk, use_container_width=True)
                            c1, c2 = st.columns(2)
                            if c1.button("✅ Aprobar", key=f"a_{d}_{m_a}"):
                                registrar_db("movimientos", {"dpto": d, "monto": mon, "tipo": "VALIDACION_ADMIN", "mes_anio": m_a, "notas": "APROBADO"})
                                st.rerun()
                            if c2.button("❌ Rechazar", key=f"r_{d}_{m_a}"):
                                registrar_db("movimientos", {"dpto": d, "monto": mon, "tipo": "VALIDACION_ADMIN", "mes_anio": m_a, "notas": "RECHAZADO"})
                                st.rerun()
        if not pendientes: st.success("Sin pendientes.")

    elif is_admin and choice == "Cargar Deudas":
        st.header("📈 Cargar Cuotas")
        c1, c2 = st.columns(2)
        mes = c1.selectbox("Mes", ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"])
        anio = c2.selectbox("Año", [2025, 2026, 2027], index=1)
        mes_a = f"{mes} {anio}"
        df_act = get_movimientos(mes_anio=mes_a)
        d_list = ["101","102","201","202","301","302","401","402","501","502","601","602","701","702","801"]
        m_ini = []
        for d in d_list:
            cobro = df_act[(df_act['dpto'] == d) & (df_act['tipo'] == 'COBRO_MENSUAL')]
            m_ini.append(float(cobro.iloc[-1]['monto']) if not cobro.empty else 0.0)
        df_ed = st.data_editor(pd.DataFrame({'Dpto': d_list, 'Monto': m_ini}), hide_index=True, key=f"ed_{mes_a}")
        if st.button("Guardar"):
            for _, r in df_ed.iterrows():
                if r['Monto'] > 0: registrar_db("movimientos", {"dpto": r['Dpto'], "monto": r['Monto'], "tipo": "COBRO_MENSUAL", "mes_anio": mes_a, "notas": "Carga"})
            st.rerun()

    elif is_admin and choice == "Registrar Gastos":
        st.header("💸 Registrar Gasto")
        with st.form("g"):
            f = st.date_input("Fecha")
            c = st.selectbox("Categoría", ["Luz", "Agua", "Mantenimiento", "Limpieza", "Otros"])
            d = st.text_input("Descripción")
            m = st.number_input("Monto S/", min_value=0.0)
            img = st.file_uploader("Recibo", type=['jpg','png','jpeg'])
            if st.form_submit_button("Guardar Gasto") and img and d:
                res = requests.post(f"https://api.imgbb.com/1/upload?key={IMG_BB_API_KEY}", files={"image": img}).json()
                registrar_db("gastos", {"fecha_gasto": str(f), "categoria": c, "descripcion": d, "monto": m, "link_factura": res['data']['url']})
                st.success("Gasto guardado"); st.rerun()

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
                f_p = st.file_uploader("Voucher", type=['jpg','png','jpeg'])
                if st.button("Enviar Pago") and f_p:
                    r_i = requests.post(f"https://api.imgbb.com/1/upload?key={IMG_BB_API_KEY}", files={"image": f_p}).json()
                    registrar_db("movimientos", {"dpto": st.session_state.user, "monto": mon, "tipo": "PAGO_VECINO", "mes_anio": m_sel, "link_comprobante": r_i['data']['url']})
                    st.rerun()
        else: st.info("No hay deudas.")

    elif not is_admin and choice == "Ver Gastos":
        st.header("📊 Gastos del Edificio")
        df_g = get_gastos()
        if not df_g.empty:
            for i, row in df_g.iterrows():
                with st.container(border=True):
                    col1, col2, col3 = st.columns([1, 2, 1])
                    col1.write(f"📅 **{row['fecha_gasto'].strftime('%Y-%m-%d')}**")
                    col2.write(f"📌 **{row['categoria']}**: {row['descripcion']}")
                    col3.write(f"💰 **S/ {row['monto']:,.2f}**")
                    if st.button("Ver Comprobante", key=f"btn_g_{row['id']}"):
                        st.image(row['link_factura'], use_container_width=True)
        else: st.info("No hay gastos registrados.")
