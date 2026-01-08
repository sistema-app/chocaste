import streamlit as st
import pandas as pd
import plotly.express as px
import time
from io import BytesIO
from difflib import SequenceMatcher

# Aumentamos límite de renderizado por si acaso
pd.set_option("styler.render.max_elements", 2000000)

# --- 1. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Reporte Unificado de Precios",
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
    if isinstance(x, str):
        clean = x.replace('$', '').replace(',', '').strip()
        try: return float(clean)
        except: return 0.0
    return x

def determine_status(val):
    if pd.isna(val): return "Sin Info"
    if abs(val) < 0.005: return 'Precio sin cambios'
    elif val > 0: return 'Precio subió'
    else: return 'Precio bajó'

def calculate_similarity(row):
    desc_erp = str(row['Descripción_Insignia']).lower().strip()
    desc_prov = str(row['Desc_Prov']).lower().strip()
    if not desc_erp or desc_erp == 'nan' or not desc_prov or desc_prov == 'nan':
        return 0.0
    return SequenceMatcher(None, desc_erp, desc_prov).ratio() * 100

def load_data(file):
    try:
        if file.name.endswith('.csv'): return pd.read_csv(file)
        else: return pd.read_excel(file)
    except Exception as e:
        st.error(f"Error cargando archivo {file.name}: {e}")
        return None

# --- 4. GESTIÓN DE ESTADO ---
if 'analyzed' not in st.session_state: st.session_state['analyzed'] = False
if 'final_report' not in st.session_state: st.session_state['final_report'] = None
if 'audit_data' not in st.session_state: st.session_state['audit_data'] = {}
if 'input_counts' not in st.session_state: st.session_state['input_counts'] = {}

# --- 5. INTERFAZ: BARRA LATERAL ---
with st.sidebar:
    st.header("📂 Panel de Control")
    st.info("Carga los archivos para generar el reporte unificado.")
    
    erp_file = st.file_uploader("Cargar BD ERP (A1)", type=['xlsx', 'csv'], key="erp")
    st.markdown("---")
    prov_pub_file = st.file_uploader("Precio Público (B1)", type=['xlsx', 'csv'], key="pub")
    prov_cost_file = st.file_uploader("Precio Costo (B2)", type=['xlsx', 'csv'], key="cost")
    st.markdown("---")
    click_analysis = st.button("🚀 Generar Reporte Unificado")

# --- 6. LÓGICA PRINCIPAL ---
st.title("🖥️ Análisis Comparativo Unificado")
st.markdown("##### Auditoría de precios, costos y similitud de catálogos")
st.divider()

if click_analysis:
    if erp_file is None:
        st.error("⚠️ Error: El archivo ERP (A1) es obligatorio.")
        st.session_state['analyzed'] = False
    elif prov_pub_file is None:
        st.error("⚠️ Error: El archivo de Precio Público (B1) es necesario.")
        st.session_state['analyzed'] = False
    else:
        progress_bar = st.progress(0, text="Iniciando motor de análisis...")
        try:
            # --- PASO 1: PROCESAR ERP ---
            df_erp = load_data(erp_file)
            erp_subset = df_erp.iloc[:, [0, 2, 18, 14, 20]].copy()
            erp_subset.columns = ['Codigo_Insignia', 'Descripción_Insignia', 'Codigo_ERP', 'Precio_Publico_ERP', 'Precio_Costo_ERP']
            
            erp_subset['Codigo_ERP'] = erp_subset['Codigo_ERP'].astype(str).str.strip()
            erp_subset['Codigo_Insignia'] = erp_subset['Codigo_Insignia'].astype(str).str.strip()
            erp_subset['Descripción_Insignia'] = erp_subset['Descripción_Insignia'].astype(str).str.strip()
            erp_subset['Precio_Publico_ERP'] = erp_subset['Precio_Publico_ERP'].apply(clean_currency).round(2)
            erp_subset['Precio_Costo_ERP'] = erp_subset['Precio_Costo_ERP'].apply(clean_currency).round(2)
            
            set_erp_codes = set(erp_subset['Codigo_ERP'])
            
            # --- PASO 2: PROCESAR PÚBLICO ---
            progress_bar.progress(25, text="Procesando Precios Públicos...")
            df_pub = load_data(prov_pub_file)
            pub_subset = df_pub.iloc[:, [0, 1, 2]].copy()
            pub_subset.columns = ['Codigo_Prov', 'Desc_Prov', 'Precio_Publico_Prov']
            pub_subset['Codigo_Prov'] = pub_subset['Codigo_Prov'].astype(str).str.strip()
            pub_subset['Desc_Prov'] = pub_subset['Desc_Prov'].astype(str).str.strip()
            pub_subset['Precio_Publico_Prov'] = pub_subset['Precio_Publico_Prov'].apply(clean_currency).round(2)
            
            set_pub_codes = set(pub_subset['Codigo_Prov'])

            # --- PASO 3: MERGE ---
            df_main = pd.merge(pub_subset, erp_subset, left_on='Codigo_Prov', right_on='Codigo_ERP', how='inner')

            # --- PASO 4: CÁLCULOS PÚBLICOS ---
            df_main['Diferencia_$$'] = (df_main['Precio_Publico_Prov'] - df_main['Precio_Publico_ERP']).round(2)
            df_main['Diferencia_%'] = df_main.apply(lambda x: ((x['Diferencia_$$'] / x['Precio_Publico_ERP']) * 100) if x['Precio_Publico_ERP'] != 0 else 0.0, axis=1).round(2)
            df_main['Estado'] = df_main['Diferencia_$$'].apply(determine_status)
            
            # Similitud (Puede tardar un poco)
            df_main['Porcentaje_Similitud_Descripcion'] = df_main.apply(calculate_similarity, axis=1).round(2)

            # --- PASO 5: COSTOS ---
            progress_bar.progress(60, text="Integrando Costos...")
            if prov_cost_file:
                df_cost = load_data(prov_cost_file)
                cost_subset = df_cost.iloc[:, [0, 9]].copy()
                cost_subset.columns = ['Codigo_Prov', 'Precio_Costo_Prov']
                cost_subset['Codigo_Prov'] = cost_subset['Codigo_Prov'].astype(str).str.strip()
                cost_subset['Precio_Costo_Prov'] = cost_subset['Precio_Costo_Prov'].apply(clean_currency).round(2)
                
                df_final = pd.merge(df_main, cost_subset[['Codigo_Prov', 'Precio_Costo_Prov']], on='Codigo_Prov', how='left')
                
                df_final['Diferencia_$$_Costo'] = (df_final['Precio_Costo_Prov'] - df_final['Precio_Costo_ERP']).round(2)
                df_final['Diferencia_%_Costo'] = df_final.apply(lambda x: ((x['Diferencia_$$_Costo'] / x['Precio_Costo_ERP']) * 100) if (pd.notnull(x['Precio_Costo_ERP']) and x['Precio_Costo_ERP'] != 0) else 0.0, axis=1).round(2)
                df_final['Estado_Costo'] = df_final['Diferencia_$$_Costo'].apply(determine_status)
            else:
                df_final = df_main.copy()
                df_final['Precio_Costo_Prov'] = 0.0
                df_final['Diferencia_$$_Costo'] = 0.0
                df_final['Diferencia_%_Costo'] = 0.0
                df_final['Estado_Costo'] = "Sin Info Costo"

            # --- PASO 6: ESTRUCTURA FINAL ---
            reporte_unificado = df_final[[
                'Codigo_Insignia', 'Descripción_Insignia', 'Desc_Prov', 'Porcentaje_Similitud_Descripcion',
                'Codigo_Prov', 'Precio_Publico_ERP', 'Precio_Publico_Prov', 'Diferencia_$$', 'Diferencia_%', 'Estado',
                'Precio_Costo_ERP', 'Precio_Costo_Prov', 'Diferencia_$$_Costo', 'Diferencia_%_Costo', 'Estado_Costo'
            ]].copy()
            
            reporte_unificado.rename(columns={
                'Diferencia_$$_Costo': 'Diferencia_$$ (Costo)',
                'Diferencia_%_Costo': 'Diferencia_% (Costo)',
                'Estado_Costo': 'Estado (Costo)'
            }, inplace=True)

            # Auditoría
            audit = {}
            audit['En_Prov_No_ERP'] = pub_subset[~pub_subset['Codigo_Prov'].isin(set_erp_codes)]
            audit['En_ERP_No_Prov'] = erp_subset[~erp_subset['Codigo_ERP'].isin(set_pub_codes)]
            
            st.session_state['final_report'] = reporte_unificado
            st.session_state['audit_data'] = audit
            st.session_state['input_counts'] = {
                'ERP': len(df_erp), 'Pub': len(df_pub), 'Cost': len(df_cost) if prov_cost_file else 0
            }
            st.session_state['analyzed'] = True
            
            progress_bar.progress(100, text="¡Análisis Completado!")
            time.sleep(0.5)
            progress_bar.empty()

        except Exception as e:
            st.error(f"❌ Error crítico: {e}")
            st.session_state['analyzed'] = False

# --- 7. VISUALIZACIÓN OPTIMIZADA ---
if st.session_state['analyzed']:
    df = st.session_state['final_report']
    counts = st.session_state['input_counts']
    audit = st.session_state['audit_data']

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Registros ERP", f"{counts['ERP']:,}")
    c2.metric("Registros Público", f"{counts['Pub']:,}")
    c3.metric("Registros Costo", f"{counts['Cost']:,}")
    avg_sim = df['Porcentaje_Similitud_Descripcion'].mean()
    c4.metric("Similitud Promedio", f"{avg_sim:.1f}%")

    st.divider()

    tab_main, tab_audit = st.tabs(["📊 Reporte Unificado", "🔍 Auditoría"])

    with tab_main:
        st.subheader("Vista Previa (Primeros 1,000 registros)")
        st.caption("ℹ️ Se muestran solo las primeras filas para mayor velocidad. El archivo descargable contiene TODO.")
        
        # Funciones de color
        def color_status(val):
            if val == 'Precio subió': return 'color: #EF553B; font-weight: bold'
            elif val == 'Precio bajó': return 'color: #636EFA; font-weight: bold'
            elif val == 'Precio sin cambios': return 'color: #00CC96'
            return ''
            
        def color_similitud(val):
            if pd.isna(val): return ''
            if val < 50: return 'color: #EF553B; font-weight: bold'
            elif val < 80: return 'color: #FFA15A'
            return 'color: #00CC96'

        # OPTIMIZACIÓN: Solo mostramos df.head(1000) en pantalla
        # Esto evita que el navegador se congele
        preview_df = df.head(1000)

        st.dataframe(
            preview_df.style.format({
                'Precio_Publico_ERP': '${:,.2f}', 'Precio_Publico_Prov': '${:,.2f}',
                'Diferencia_$$': '${:,.2f}', 'Diferencia_%': '{:.2f}%',
                'Porcentaje_Similitud_Descripcion': '{:.1f}%',
                'Precio_Costo_ERP': '${:,.2f}', 'Precio_Costo_Prov': '${:,.2f}',
                'Diferencia_$$ (Costo)': '${:,.2f}', 'Diferencia_% (Costo)': '{:.2f}%'
            })
            .map(color_status, subset=['Estado', 'Estado (Costo)']) 
            .map(color_similitud, subset=['Porcentaje_Similitud_Descripcion']),
            use_container_width=True
        )

        # Descarga Excel (USA EL DATAFRAME COMPLETO 'df', NO EL PREVIEW)
        output = BytesIO()
        try:
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='Reporte_Unificado')
        except:
            with pd.ExcelWriter(output) as writer:
                df.to_excel(writer, index=False, sheet_name='Reporte_Unificado')
        
        st.download_button(
            label="📥 Descargar Reporte Completo (Excel)",
            data=output.getvalue(),
            file_name="Reporte_Precios_Unificado.xlsx",
            mime="application/vnd.ms-excel"
        )

    with tab_audit:
        c_a, c_b = st.columns(2)
        with c_a:
            st.warning(f"En Proveedor pero NO en ERP: {len(audit['En_Prov_No_ERP'])}")
            st.dataframe(audit['En_Prov_No_ERP'].head(1000), use_container_width=True)
        with c_b:
            st.info(f"En ERP pero NO en Proveedor: {len(audit['En_ERP_No_Prov'])}")
            st.dataframe(audit['En_ERP_No_Prov'][['Codigo_ERP','Precio_Publico_ERP']].head(1000), use_container_width=True)

else:
    st.markdown("<div style='text-align: center; margin-top: 50px; opacity: 0.7;'><h3>👋 Bienvenido</h3><p>Carga los archivos para generar el análisis.</p></div>", unsafe_allow_html=True)