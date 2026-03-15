import streamlit as st
import biosteam as bst
import thermosteam as tmo
import pandas as pd
import google.generativeai as genai

# =================================================================
# 1. CONFIGURACIÓN DE LA PÁGINA
# =================================================================
st.set_page_config(page_title="BioSim Pro | Destilación Flash", layout="wide")

# CSS para mejorar la estética
st.markdown("""
    <style>
    .stDataFrame { border: 1px solid #e6e9ef; border-radius: 10px; }
    .stGraphvizChart { display: flex; justify-content: center; }
    </style>
    """, unsafe_allow_html=True)

# =================================================================
# 2. LÓGICA DE SIMULACIÓN
# =================================================================
def run_simulation(f_water, f_eth, t_feed, p_flash):
    # Limpiar el flowsheet para evitar errores de IDs duplicados en cada ejecución
    bst.main_flowsheet.clear()
    chemicals = tmo.Chemicals(["Water", "Ethanol"])
    bst.settings.set_thermo(chemicals)

    # Corrientes
    mosto = bst.Stream("mosto", Water=f_water, Ethanol=f_eth, units="kg/hr", T=t_feed + 273.15, P=101325)
    vinazas_retorno = bst.Stream("Vinazas_Retorno", Water=200, T=95+273.15, P=300000)

    # Equipos
    P100 = bst.Pump("P100", ins=mosto, P=4*101325)
    W210 = bst.HXprocess("W210", ins=(P100-0, vinazas_retorno), outs=("Mosto_Pre", "Drenaje"), phase0='l', phase1='l')
    W210.outs[0].T = 85 + 273.15
    
    W220 = bst.HXutility("W220", ins=W210-0, outs="Mezcla", T=92+273.15)
    V100 = bst.IsenthalpicValve("V100", ins=W220-0, outs="Mezcla_Bifasica", P=p_flash)
    
    # Flash configurado para evitar error de duty (Q=0 es adiabático)
    V1 = bst.Flash("V1", ins=V100-0, outs=("Vapor_caliente", "Vinazas"), P=p_flash, Q=0)
    
    W310 = bst.HXutility("W310", ins=V1-0, outs="Producto_Final", T=25+273.15)
    P200 = bst.Pump("P200", ins=V1-1, outs=vinazas_retorno, P=3*101325)

    sys = bst.System("eth_sys", path=(P100, W210, W220, V100, V1, W310, P200))
    sys.simulate()
    return sys

def generar_reportes(sistema):
    # Reporte de Materia
    m_data = []
    for s in sistema.streams:
        if s.F_mass > 0:
            m_data.append({
                "Corriente": s.ID,
                "Temp (°C)": round(s.T - 273.15, 2),
                "Flujo (kg/h)": round(s.F_mass, 2),
                "Etanol %": round((s.imass['Ethanol']/s.F_mass)*100, 1) if s.F_mass > 0 else 0
            })
    
    # Reporte de Energía
    e_data = []
    for u in sistema.units:
        # Verificación segura de atributos de energía
        calor = 0.0
        if hasattr(u, 'duty'):
            calor = u.duty / 3600
        elif isinstance(u, bst.HXprocess):
            calor = (u.outs[0].H - u.ins[0].H) / 3600
            
        potencia = u.power_utility.rate if u.power_utility else 0
        
        if abs(calor) > 0.01 or potencia > 0.01:
            e_data.append({
                "Equipo": u.ID,
                "Calor (kW)": round(calor, 2),
                "Potencia Eléctrica (kW)": round(potencia, 2)
            })
            
    return pd.DataFrame(m_data), pd.DataFrame(e_data)

# =================================================================
# 3. INTERFAZ DE USUARIO (LAYOUT COLUMNAS)
# =================================================================
st.title("🧪 BioSim Pro: Purificación de Etanol")
st.markdown("---")

# Sidebar
with st.sidebar:
    st.header("📥 Parámetros de Entrada")
    f_w = st.slider("Flujo Agua (kg/h)", 500, 2000, 900)
    f_e = st.slider("Flujo Etanol (kg/h)", 10, 500, 100)
    p_f = st.number_input("Presión de Flash (Pa)", value=101325)
    
    st.divider()
    # Usar secrets de Streamlit o input manual
    api_key = st.text_input("Gemini API Key", type="password", help="Pega tu clave de Google AI Studio")

# Botón de ejecución
if st.button("🚀 Ejecutar Simulación", use_container_width=True):
    try:
        sys = run_simulation(f_w, f_e, 25, p_f)
        df_m, df_e = generar_reportes(sys)

        # Layout: Diagrama arriba, tablas abajo en columnas
        st.subheader("📊 Diagrama de Flujo de Proceso (PFD)")
        st.graphviz_chart(sys.diagram('dot'))

        st.markdown("---")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📋 Balance de Materia")
            st.dataframe(df_m, use_container_width=True, hide_index=True)
            
        with col2:
            st.subheader("⚡ Balance de Energía")
            st.dataframe(df_e, use_container_width=True, hide_index=True)

        # --- SECCIÓN IA ---
        if api_key:
            st.divider()
            st.subheader("🤖 Consultoría Técnica (Gemini AI)")
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-2.5-pro')
            
            prompt = f"""
            Como experto en termodinámica, analiza estos resultados de BioSTEAM:
            - Corrientes: {df_m.to_dict()}
            - Energía: {df_e.to_dict()}
            Explica brevemente si el tanque Flash está separando bien el etanol y qué pasaría si bajo la presión.
            """
            with st.spinner("IA analizando datos..."):
                response = model.generate_content(prompt)
                st.info(response.text)
        else:
            st.warning("⚠️ Configura la API Key en el panel izquierdo para recibir consejos de la IA.")

    except Exception as e:
        st.error(f"Se produjo un error: {e}")
        st.info("Tip: Asegúrate de que los flujos no sean cero.")
else:
    st.light_circle = "Esperando parámetros..."
    st.info("Configura los valores en la izquierda y presiona el botón para iniciar.")
