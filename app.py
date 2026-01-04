import streamlit as st
import pandas as pd
import plotly.express as px
import time
from io import BytesIO

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
    """Limpia formatos de moneda ($ 1,200.00 -> 1200.0)"""
    if isinstance(x, str):
        clean = x.replace('$', '').replace(',', '').strip()
        try: return float(clean)
        except: return 0.0
    return x

def determine_status(val):
    """
    Función única para determinar estado (subió, bajó, igual).
    Aplica tolerancia de 0.005.
    """
    if pd.isna(val):
        return "Sin Info"
    
    if abs(val) < 0.005: 
        return 'Precio sin cambios'
    elif val > 0: 
        return 'Precio subió'
    else: 
        return 'Precio bajó'

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
    st.info("Para generar el reporte unificado, se recomienda cargar los 3 archivos.")
    
    st.markdown("### 1. Base de Datos ERP (A1)")
    erp_file = st.file_uploader("Cargar BD ERP", type=['xlsx', 'csv'], key="erp")
    
    st.markdown("---")
    st.markdown("### 2. Archivos de Proveedor")
    prov_pub_file = st.file_uploader("Lista Precio Público (B1)", type=['xlsx', 'csv'], key="pub")
    prov_cost_file = st.file_uploader("Lista Precio Costo (B2)", type=['xlsx', 'csv'], key="cost")

    st.markdown("---")
    click_analysis = st.button("🚀 Generar Reporte Unificado")

# --- 6. LÓGICA PRINCIPAL (REFACTORIZADA) ---
st.title("🖥️ Análisis Comparativo Unificado")
st.markdown("##### Consolidación de Precios Públicos y Costos en un solo reporte")
st.divider()

if click_analysis:
    # Validaciones mínimas
    if erp_file is None:
        st.error("⚠️ Error: El archivo ERP (A1) es obligatorio.")
        st.session_state['analyzed'] = False
    elif prov_pub_file is None:
        st.error("⚠️ Error: El archivo de Precio Público (B1) es necesario para la estructura base.")
        st.session_state['analyzed'] = False
    else:
        progress_bar = st.progress(0, text="Iniciando motor de unificación...")
        try:
            # --- PASO 1: PROCESAR ERP (A1) ---
            df_erp = load_data(erp_file)
            # A=0(Insignia), O=14(Pub), S=18(Cod), U=20(Cost)
            erp_subset = df_erp.iloc[:, [0, 18, 14, 20]].copy()
            erp_subset.columns = ['Codigo_Insignia', 'Codigo_ERP', 'Precio_Publico_ERP', 'Precio_Costo_ERP']
            
            # Limpieza ERP
            erp_subset['Codigo_ERP'] = erp_subset['Codigo_ERP'].astype(str).str.strip()
            erp_subset['Codigo_Insignia'] = erp_subset['Codigo_Insignia'].astype(str).str.strip()
            erp_subset['Precio_Publico_ERP'] = erp_subset['Precio_Publico_ERP'].apply(clean_currency).round(2)
            erp_subset['Precio_Costo_ERP'] = erp_subset['Precio_Costo_ERP'].apply(clean_currency).round(2)
            
            set_erp_codes = set(erp_subset['Codigo_ERP'])
            
            # --- PASO 2: PROCESAR PÚBLICO (B1) - BASE DEL REPORTE ---
            progress_bar.progress(25, text="Procesando Precios Públicos...")
            df_pub = load_data(prov_pub_file)
            # A=0(Cod), B=1(Desc), C=2(Pub)
            pub_subset = df_pub.iloc[:, [0, 1, 2]].copy()
            pub_subset.columns = ['Codigo_Prov', 'Desc_Prov', 'Precio_Publico_Prov']
            pub_subset['Codigo_Prov'] = pub_subset['Codigo_Prov'].astype(str).str.strip()
            pub_subset['Precio_Publico_Prov'] = pub_subset['Precio_Publico_Prov'].apply(clean_currency).round(2)
            
            set_pub_codes = set(pub_subset['Codigo_Prov'])

            # --- PASO 3: MERGE BASE (ERP + PÚBLICO) ---
            # Inner Join: Solo lo que existe en ambos define las filas del reporte
            df_main = pd.merge(
                pub_subset,
                erp_subset,
                left_on='Codigo_Prov',
                right_on='Codigo_ERP',
                how='inner'
            )

            # --- PASO 4: CÁLCULOS PÚBLICOS ---
            df_main['Diferencia_$$'] = (df_main['Precio_Publico_Prov'] - df_main['Precio_Publico_ERP']).round(2)
            df_main['Diferencia_%'] = df_main.apply(
                lambda x: ((x['Diferencia_$$'] / x['Precio_Publico_ERP']) * 100) if x['Precio_Publico_ERP'] != 0 else 0.0, axis=1
            ).round(2)
            df_main['Estado'] = df_main['Diferencia_$$'].apply(determine_status)

            # Campos pendientes
            df_main['Descripción_Insignia'] = None
            df_main['Porcentaje_Similitud_Descripcion'] = None

            # --- PASO 5: INTEGRACIÓN DE COSTOS (B2) ---
            progress_bar.progress(50, text="Integrando Costos...")
            
            if prov_cost_file:
                df_cost = load_data(prov_cost_file)
                # A=0(Cod), J=9(Cost)
                cost_subset = df_cost.iloc[:, [0, 9]].copy()
                cost_subset.columns = ['Codigo_Prov', 'Precio_Costo_Prov']
                cost_subset['Codigo_Prov'] = cost_subset['Codigo_Prov'].astype(str).str.strip()
                cost_subset['Precio_Costo_Prov'] = cost_subset['Precio_Costo_Prov'].apply(clean_currency).round(2)
                
                set_cost_codes = set(cost_subset['Codigo_Prov'])
                
                # LEFT JOIN: Mantenemos la estructura del reporte público. 
                # Si no hay costo en B2 para un artículo, quedará vacío/NaN.
                df_final = pd.merge(
                    df_main,
                    cost_subset[['Codigo_Prov', 'Precio_Costo_Prov']],
                    on='Codigo_Prov',
                    how='left'
                )
                
                # Cálculos Costos
                # Nota: Si Precio_Costo_Prov es NaN, las diferencias serán NaN
                df_final['Diferencia_$$_Costo'] = (df_final['Precio_Costo_Prov'] - df_final['Precio_Costo_ERP']).round(2)
                df_final['Diferencia_%_Costo'] = df_final.apply(
                    lambda x: ((x['Diferencia_$$_Costo'] / x['Precio_Costo_ERP']) * 100) if (pd.notnull(x['Precio_Costo_ERP']) and x['Precio_Costo_ERP'] != 0) else 0.0, axis=1
                ).round(2)
                df_final['Estado_Costo'] = df_final['Diferencia_$$_Costo'].apply(determine_status)
                
            else:
                # Si no se carga archivo de costos, creamos las columnas vacías
                df_final = df_main.copy()
                df_final['Precio_Costo_Prov'] = 0.0
                df_final['Diferencia_$$_Costo'] = 0.0
                df_final['Diferencia_%_Costo'] = 0.0
                df_final['Estado_Costo'] = "Sin Info Costo"
                set_cost_codes = set()

            # --- PASO 6: ESTRUCTURACIÓN FINAL DEL REPORTE ---
            # Orden estricto solicitado:
            # 1-10: Público (A-J)
            # 11-15: Costos (K-O)
            
            reporte_unificado = df_final[[
                # --- BLOQUE PÚBLICO ---
                'Codigo_Insignia',                  # A
                'Descripción_Insignia',             # B (Pendiente)
                'Desc_Prov',                        # C
                'Porcentaje_Similitud_Descripcion', # D (Calculado)
                'Codigo_Prov',                      # E
                'Precio_Publico_ERP',               # F
                'Precio_Publico_Prov',              # G
                'Diferencia_$$',                    # H
                'Diferencia_%',                     # I
                'Estado',                           # J
                
                # --- BLOQUE COSTO (Nuevo) ---
                'Precio_Costo_ERP',                 # K
                'Precio_Costo_Prov',                # L
                'Diferencia_$$_Costo',              # M (Renombrado interno para evitar duplicado)
                'Diferencia_%_Costo',               # N
                'Estado_Costo'                      # O
            ]].copy()
            
            # Renombrar columnas para la salida final (Visualización y Excel)
            # Usamos paréntesis para diferenciar las columnas duplicadas conceptualmente
            columnas_finales = {
                'Diferencia_$$_Costo': 'Diferencia_$$ (Costo)',
                'Diferencia_%_Costo': 'Diferencia_% (Costo)',
                'Estado_Costo': 'Estado (Costo)'
            }
            reporte_unificado.rename(columns=columnas_finales, inplace=True)

            # --- AUDITORÍA RAPIDA ---
            audit = {}
            audit['En_Prov_No_ERP'] = pub_subset[~pub_subset['Codigo_Prov'].isin(set_erp_codes)]
            audit['En_ERP_No_Prov'] = erp_subset[~erp_subset['Codigo_ERP'].isin(set_pub_codes)]
            
            # Guardar en sesión
            st.session_state['final_report'] = reporte_unificado
            st.session_state['audit_data'] = audit
            st.session_state['input_counts'] = {
                'ERP': len(df_erp),
                'Pub': len(df_pub),
                'Cost': len(df_cost) if prov_cost_file else 0
            }
            st.session_state['analyzed'] = True
            
            progress_bar.progress(100, text="Reporte Unificado Generado")
            time.sleep(0.5)
            progress_bar.empty()

        except Exception as e:
            st.error(f"❌ Error crítico: {e}")
            st.session_state['analyzed'] = False

# --- 7. VISUALIZACIÓN ---
if st.session_state['analyzed']:
    df = st.session_state['final_report']
    counts = st.session_state['input_counts']
    audit = st.session_state['audit_data']

    # Métricas
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Registros ERP", f"{counts['ERP']:,}")
    c2.metric("Registros Público", f"{counts['Pub']:,}")
    c3.metric("Registros Costo", f"{counts['Cost']:,}")
    c4.metric("Filas Reporte Final", f"{len(df):,}")

    st.divider()

    # TABS
    tab_main, tab_audit = st.tabs(["📊 Reporte Unificado", "🔍 Auditoría (No Coincidentes)"])

    with tab_main:
        st.subheader("Vista Previa del Reporte Integrado")
        
        # Estilizado condicional para ambas columnas de Estado
        def color_status(val):
            if val == 'Precio subió': return 'color: #EF553B; font-weight: bold'
            elif val == 'Precio bajó': return 'color: #636EFA; font-weight: bold'
            elif val == 'Precio sin cambios': return 'color: #00CC96'
            return ''

        # Mostramos dataframe
        st.dataframe(
            df.style.format({
                'Precio_Publico_ERP': '${:,.2f}', 'Precio_Publico_Prov': '${:,.2f}',
                'Diferencia_$$': '${:,.2f}', 'Diferencia_%': '{:.2f}%',
                'Precio_Costo_ERP': '${:,.2f}', 'Precio_Costo_Prov': '${:,.2f}',
                'Diferencia_$$ (Costo)': '${:,.2f}', 'Diferencia_% (Costo)': '{:.2f}%'
            }).applymap(color_status, subset=['Estado', 'Estado (Costo)']),
            use_container_width=True
        )

        # Descarga
        output = BytesIO()
        try:
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='Reporte_Unificado')
        except:
            with pd.ExcelWriter(output) as writer:
                df.to_excel(writer, index=False, sheet_name='Reporte_Unificado')
        
        st.download_button(
            label="📥 Descargar Reporte Unificado (Excel)",
            data=output.getvalue(),
            file_name="Reporte_Precios_Unificado.xlsx",
            mime="application/vnd.ms-excel"
        )

    with tab_audit:
        c_a, c_b = st.columns(2)
        with c_a:
            st.warning(f"En Proveedor (Pub) pero NO en ERP: {len(audit['En_Prov_No_ERP'])}")
            st.dataframe(audit['En_Prov_No_ERP'], use_container_width=True)
        with c_b:
            st.info(f"En ERP pero NO en Proveedor (Pub): {len(audit['En_ERP_No_Prov'])}")
            st.dataframe(audit['En_ERP_No_Prov'][['Codigo_ERP','Precio_Publico_ERP']], use_container_width=True)

else:
    st.markdown("<div style='text-align: center; margin-top: 50px; opacity: 0.7;'><h3>👋 Bienvenido</h3><p>Carga los 3 archivos para obtener el reporte completo.</p></div>", unsafe_allow_html=True)