import streamlit as st
import pandas as pd
import plotly.express as px
import time
from io import BytesIO

# --- 1. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Análisis Comparativo de Archivos",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 2. ESTILOS CSS ---
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    h1 { color: #4da6ff; font-family: 'Helvetica Neue', sans-serif; }
    .stButton>button {
        background-color: #2196F3; color: white; border-radius: 8px;
        height: 3em; width: 100%; font-weight: bold; border: none;
    }
    .stButton>button:hover { background-color: #1976D2; }
    div[data-testid="stMetric"] {
        background-color: #262730; padding: 15px; border-radius: 10px;
        border-left: 5px solid #4da6ff; box-shadow: 2px 2px 5px rgba(0,0,0,0.3);
    }
    </style>
""", unsafe_allow_html=True)

# --- 3. FUNCIONES AUXILIARES ---

def clean_currency(x):
    """Limpieza de moneda ($ 1,200.00 -> 1200.0)"""
    if isinstance(x, str):
        clean = x.replace('$', '').replace(',', '').strip()
        try: return float(clean)
        except: return 0.0
    return x

def determine_status(row):
    """Estado con tolerancia para evitar errores de decimales."""
    val = row['Diferencia_$$']
    if abs(val) < 0.005: return 'Igual'
    elif val > 0: return 'Mayor que ERP'
    else: return 'Menor que ERP'

def load_data(file):
    try:
        if file.name.endswith('.csv'): return pd.read_csv(file)
        else: return pd.read_excel(file)
    except Exception as e:
        st.error(f"Error cargando archivo {file.name}: {e}")
        return None

# --- 4. GESTIÓN DE ESTADO (SESSION STATE) ---
if 'analyzed' not in st.session_state: st.session_state['analyzed'] = False
if 'res_public' not in st.session_state: st.session_state['res_public'] = None
if 'res_cost' not in st.session_state: st.session_state['res_cost'] = None

# Variables de auditoría
if 'audit_data' not in st.session_state: st.session_state['audit_data'] = {}
if 'input_counts' not in st.session_state: st.session_state['input_counts'] = {}

# --- 5. INTERFAZ: BARRA LATERAL ---
with st.sidebar:
    st.header("📂 Panel de Control")
    st.info("Carga tus archivos para comenzar.")
    
    st.markdown("### 1. Base de Datos ERP (A1)")
    erp_file = st.file_uploader("Cargar BD ERP", type=['xlsx', 'csv'], key="erp")
    
    st.markdown("---")
    st.markdown("### 2. Archivos de Proveedor")
    prov_pub_file = st.file_uploader("Lista Precio Público (B1)", type=['xlsx', 'csv'], key="pub")
    prov_cost_file = st.file_uploader("Lista Precio Costo (B2)", type=['xlsx', 'csv'], key="cost")

    st.markdown("---")
    click_analysis = st.button("🚀 Ejecutar Análisis")

# --- 6. LÓGICA PRINCIPAL ---
st.title("🖥️ Análisis Comparativo de Archivos")
st.markdown("##### Comparación cuantitativa y auditoría de catálogos")
st.divider()

if click_analysis:
    if erp_file is None:
        st.error("⚠️ Error: El archivo base del ERP (A1) es obligatorio.")
        st.session_state['analyzed'] = False
    else:
        progress_bar = st.progress(0, text="Iniciando lectura de datos...")
        try:
            # --- LEER ERP ---
            df_erp = load_data(erp_file)
            count_erp = len(df_erp)
            
            # Normalizar ERP
            erp_subset = df_erp.iloc[:, [18, 14, 20]].copy()
            erp_subset.columns = ['Codigo_ERP', 'Precio_Publico_ERP', 'Precio_Costo_ERP']
            erp_subset['Codigo_ERP'] = erp_subset['Codigo_ERP'].astype(str).str.strip()
            erp_subset['Precio_Publico_ERP'] = erp_subset['Precio_Publico_ERP'].apply(clean_currency).round(2)
            erp_subset['Precio_Costo_ERP'] = erp_subset['Precio_Costo_ERP'].apply(clean_currency).round(2)
            
            set_erp_codes = set(erp_subset['Codigo_ERP'])

            # Inicializar variables
            temp_res_public = None
            temp_res_cost = None
            audit = {}
            counts = {'ERP': count_erp, 'B1': 0, 'B2': 0}

            # --- ANÁLISIS PRECIO PÚBLICO (B1) ---
            if prov_pub_file:
                progress_bar.progress(30, text="Analizando Precio Público...")
                df_pub = load_data(prov_pub_file)
                counts['B1'] = len(df_pub)
                
                # Normalizar B1
                pub_subset = df_pub.iloc[:, [0, 1, 2]].copy()
                pub_subset.columns = ['Codigo_Prov', 'Desc_Prov', 'Precio_Publico_Prov']
                pub_subset['Codigo_Prov'] = pub_subset['Codigo_Prov'].astype(str).str.strip()
                pub_subset['Precio_Publico_Prov'] = pub_subset['Precio_Publico_Prov'].apply(clean_currency).round(2)
                
                set_pub_codes = set(pub_subset['Codigo_Prov'])

                # 1. COINCIDENCIAS
                temp_res_public = pd.merge(
                    pub_subset, erp_subset[['Codigo_ERP', 'Precio_Publico_ERP']],
                    left_on='Codigo_Prov', right_on='Codigo_ERP', how='inner'
                )
                temp_res_public['Diferencia_$$'] = (temp_res_public['Precio_Publico_Prov'] - temp_res_public['Precio_Publico_ERP']).round(2)
                temp_res_public['Diferencia_%'] = temp_res_public.apply(
                    lambda x: ((x['Diferencia_$$'] / x['Precio_Publico_ERP']) * 100) if x['Precio_Publico_ERP'] != 0 else 0.0, axis=1
                ).round(2)
                temp_res_public['Estado'] = temp_res_public.apply(determine_status, axis=1)

                # 2. AUDITORÍA
                audit['B1_not_A1'] = pub_subset[~pub_subset['Codigo_Prov'].isin(set_erp_codes)]
                audit['A1_not_B1'] = erp_subset[~erp_subset['Codigo_ERP'].isin(set_pub_codes)]

            # --- ANÁLISIS PRECIO COSTO (B2) ---
            if prov_cost_file:
                progress_bar.progress(60, text="Analizando Precio Costo...")
                df_cost = load_data(prov_cost_file)
                counts['B2'] = len(df_cost)

                # Normalizar B2
                cost_subset = df_cost.iloc[:, [0, 9]].copy()
                cost_subset.columns = ['Codigo_Prov', 'Precio_Costo_Prov']
                cost_subset['Codigo_Prov'] = cost_subset['Codigo_Prov'].astype(str).str.strip()
                cost_subset['Precio_Costo_Prov'] = cost_subset['Precio_Costo_Prov'].apply(clean_currency).round(2)
                
                set_cost_codes = set(cost_subset['Codigo_Prov'])

                # 1. COINCIDENCIAS
                temp_res_cost = pd.merge(
                    cost_subset, erp_subset[['Codigo_ERP', 'Precio_Costo_ERP']],
                    left_on='Codigo_Prov', right_on='Codigo_ERP', how='inner'
                )
                temp_res_cost['Diferencia_$$'] = (temp_res_cost['Precio_Costo_Prov'] - temp_res_cost['Precio_Costo_ERP']).round(2)
                temp_res_cost['Diferencia_%'] = temp_res_cost.apply(
                    lambda x: ((x['Diferencia_$$'] / x['Precio_Costo_ERP']) * 100) if x['Precio_Costo_ERP'] != 0 else 0.0, axis=1
                ).round(2)
                temp_res_cost['Estado'] = temp_res_cost.apply(determine_status, axis=1)

                # 2. AUDITORÍA
                audit['B2_not_A1'] = cost_subset[~cost_subset['Codigo_Prov'].isin(set_erp_codes)]
                audit['A1_not_B2'] = erp_subset[~erp_subset['Codigo_ERP'].isin(set_cost_codes)]

            # GUARDAR ESTADO
            st.session_state['res_public'] = temp_res_public
            st.session_state['res_cost'] = temp_res_cost
            st.session_state['audit_data'] = audit
            st.session_state['input_counts'] = counts
            st.session_state['analyzed'] = True

            progress_bar.progress(100, text="¡Análisis finalizado!")
            time.sleep(0.5)
            progress_bar.empty()

        except Exception as e:
            st.error(f"❌ Error crítico: {e}")
            st.session_state['analyzed'] = False

# --- 7. VISUALIZACIÓN DE RESULTADOS ---
if st.session_state['analyzed']:
    res_public = st.session_state['res_public']
    res_cost = st.session_state['res_cost']
    audit = st.session_state['audit_data']
    counts = st.session_state['input_counts']

    # --- METRICAS GLOBALES ---
    st.subheader("📋 Resumen de Carga")
    m1, m2, m3 = st.columns(3)
    m1.metric("Registros en ERP (A1)", f"{counts['ERP']:,}")
    m2.metric("Registros Público (B1)", f"{counts['B1']:,}" if counts['B1'] > 0 else "No cargado", delta_color="off")
    m3.metric("Registros Costo (B2)", f"{counts['B2']:,}" if counts['B2'] > 0 else "No cargado", delta_color="off")

    st.divider()
    
    # TABS
    tab1, tab2, tab3 = st.tabs(["💰 Análisis Precio Público", "📉 Análisis Precio Costo", "🔍 Auditoría de Cruces"])

    # === PESTAÑA 1: PRECIO PÚBLICO ===
    with tab1:
        if res_public is not None:
            real_diffs = res_public[res_public['Estado'] != 'Igual']
            
            # KPIs SIMPLIFICADOS (Solo 2 columnas)
            k1, k2 = st.columns(2)
            k1.metric("Items Cruzados (Coincidentes)", f"{len(res_public)}")
            k2.metric("Discrepancias Reales", f"{len(real_diffs)}", delta_color="inverse")
            
            # Gráfico Pastel
            st.subheader("Distribución de Estatus")
            df_pie = res_public['Estado'].value_counts().reset_index()
            df_pie.columns = ['Estado', 'Cantidad']
            fig_pie = px.pie(df_pie, values='Cantidad', names='Estado', 
                             color='Estado', hole=0.4,
                             color_discrete_map={'Igual':'#00CC96', 'Mayor que ERP':'#EF553B', 'Menor que ERP':'#636EFA'})
            st.plotly_chart(fig_pie, use_container_width=True)
            
            # Tabla
            st.dataframe(res_public[['Codigo_Prov', 'Desc_Prov', 'Precio_Publico_ERP', 'Precio_Publico_Prov', 'Diferencia_$$', 'Diferencia_%', 'Estado']].style.format({'Precio_Publico_ERP': '${:,.2f}', 'Precio_Publico_Prov': '${:,.2f}', 'Diferencia_$$': '${:,.2f}', 'Diferencia_%': '{:.2f}%'}).applymap(lambda v: 'color: #EF553B' if v == 'Mayor que ERP' else ('color: #636EFA' if v == 'Menor que ERP' else 'color: #00CC96'), subset=['Estado']), use_container_width=True)

            # Descarga
            output = BytesIO()
            try:
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    res_public.to_excel(writer, index=False, sheet_name='Analisis_Publico')
            except:
                with pd.ExcelWriter(output) as writer:
                    res_public.to_excel(writer, index=False, sheet_name='Analisis_Publico')
            st.download_button("📥 Descargar Reporte Público", output.getvalue(), "Reporte_Publico.xlsx")
        else:
            st.info("No se cargó archivo de Precios Públicos.")

    # === PESTAÑA 2: PRECIO COSTO ===
    with tab2:
        if res_cost is not None:
            c1, c2, c3 = st.columns(3)
            c1.metric("Items Cruzados", f"{len(res_cost)}")
            c2.metric("Aumentos Costo", f"{len(res_cost[res_cost['Estado'] == 'Mayor que ERP'])}", delta_color="inverse")
            c3.metric("Reducciones Costo", f"{len(res_cost[res_cost['Estado'] == 'Menor que ERP'])}", delta_color="normal")

            # Scatter
            fig_sc = px.scatter(res_cost, x='Precio_Costo_ERP', y='Precio_Costo_Prov', color='Estado', 
                                color_discrete_map={'Igual':'#00CC96', 'Mayor que ERP':'#EF553B', 'Menor que ERP':'#636EFA'},
                                hover_data=['Codigo_Prov'], title="Mapa de Dispersión Costos")
            max_v = max(res_cost['Precio_Costo_ERP'].max(), res_cost['Precio_Costo_Prov'].max()) if not res_cost.empty else 100
            fig_sc.add_shape(type="line", line=dict(dash="dash", color="gray"), x0=0, y0=0, x1=max_v, y1=max_v)
            st.plotly_chart(fig_sc, use_container_width=True)

            # Tabla
            st.dataframe(res_cost.style.format({'Precio_Costo_ERP': '${:,.2f}', 'Precio_Costo_Prov': '${:,.2f}', 'Diferencia_$$': '${:,.2f}', 'Diferencia_%': '{:.2f}%'}).applymap(lambda v: 'color: #EF553B' if v == 'Mayor que ERP' else ('color: #636EFA' if v == 'Menor que ERP' else 'color: #00CC96'), subset=['Estado']), use_container_width=True)

            # Descarga
            output_c = BytesIO()
            try:
                with pd.ExcelWriter(output_c, engine='xlsxwriter') as writer:
                    res_cost.to_excel(writer, index=False, sheet_name='Analisis_Costo')
            except:
                with pd.ExcelWriter(output_c) as writer:
                    res_cost.to_excel(writer, index=False, sheet_name='Analisis_Costo')
            st.download_button("📥 Descargar Reporte Costos", output_c.getvalue(), "Reporte_Costos.xlsx")
        else:
            st.info("No se cargó archivo de Precios de Costo.")

    # === PESTAÑA 3: AUDITORÍA DE CRUCES ===
    with tab3:
        st.subheader("🔍 Registros No Coincidentes")
        st.markdown("Identificación de códigos que existen en un archivo pero no en el otro.")
        
        # Auditoría Público
        if res_public is not None:
            st.markdown("#### 1. Cruce: Proveedor Público (B1) vs ERP (A1)")
            col_a, col_b = st.columns(2)
            with col_a:
                df_b1_no_a1 = audit.get('B1_not_A1')
                st.error(f"En Proveedor pero NO en ERP: {len(df_b1_no_a1)} registros")
                if not df_b1_no_a1.empty:
                    st.dataframe(df_b1_no_a1, height=200, use_container_width=True)
                else:
                    st.success("✅ Todos los códigos del proveedor existen en ERP.")

            with col_b:
                df_a1_no_b1 = audit.get('A1_not_B1')
                st.warning(f"En ERP pero NO en Proveedor: {len(df_a1_no_b1)} registros")
                if not df_a1_no_b1.empty:
                    st.dataframe(df_a1_no_b1[['Codigo_ERP', 'Precio_Publico_ERP']], height=200, use_container_width=True)

        st.divider()

        # Auditoría Costo
        if res_cost is not None:
            st.markdown("#### 2. Cruce: Proveedor Costo (B2) vs ERP (A1)")
            col_c, col_d = st.columns(2)
            with col_c:
                df_b2_no_a1 = audit.get('B2_not_A1')
                st.error(f"En Proveedor Costo pero NO en ERP: {len(df_b2_no_a1)} registros")
                if not df_b2_no_a1.empty:
                    st.dataframe(df_b2_no_a1, height=200, use_container_width=True)
                else:
                    st.success("✅ Todos los códigos de costo existen en ERP.")

            with col_d:
                df_a1_no_b2 = audit.get('A1_not_B2')
                st.warning(f"En ERP pero NO en Proveedor Costo: {len(df_a1_no_b2)} registros")
                if not df_a1_no_b2.empty:
                    st.dataframe(df_a1_no_b2[['Codigo_ERP', 'Precio_Costo_ERP']], height=200, use_container_width=True)
        
        # Descarga Auditoría
        if res_public is not None or res_cost is not None:
            st.markdown("---")
            output_audit = BytesIO()
            try:
                with pd.ExcelWriter(output_audit, engine='xlsxwriter') as writer:
                    if 'B1_not_A1' in audit: audit['B1_not_A1'].to_excel(writer, index=False, sheet_name='En_Prov_No_ERP_Pub')
                    if 'A1_not_B1' in audit: audit['A1_not_B1'].to_excel(writer, index=False, sheet_name='En_ERP_No_Prov_Pub')
                    if 'B2_not_A1' in audit: audit['B2_not_A1'].to_excel(writer, index=False, sheet_name='En_Prov_No_ERP_Cost')
                    if 'A1_not_B2' in audit: audit['A1_not_B2'].to_excel(writer, index=False, sheet_name='En_ERP_No_Prov_Cost')
            except:
                 with pd.ExcelWriter(output_audit) as writer:
                    if 'B1_not_A1' in audit: audit['B1_not_A1'].to_excel(writer, index=False, sheet_name='En_Prov_No_ERP_Pub')
                    if 'A1_not_B1' in audit: audit['A1_not_B1'].to_excel(writer, index=False, sheet_name='En_ERP_No_Prov_Pub')
                    if 'B2_not_A1' in audit: audit['B2_not_A1'].to_excel(writer, index=False, sheet_name='En_Prov_No_ERP_Cost')
                    if 'A1_not_B2' in audit: audit['A1_not_B2'].to_excel(writer, index=False, sheet_name='En_ERP_No_Prov_Cost')
            
            st.download_button("📥 Descargar Reporte de Auditoría", output_audit.getvalue(), "Reporte_Auditoria_Cruces.xlsx")

else:
    st.markdown("<div style='text-align: center; margin-top: 50px; opacity: 0.7;'><h3>👋 Bienvenido</h3><p>Carga los archivos en el menú lateral y pulsa 'Ejecutar Análisis'</p></div>", unsafe_allow_html=True)