import streamlit as st
import biosteam as bst
import thermosteam as tmo
import pandas as pd
import google.generativeai as genai

# =================================================================
# 1. CONFIGURACIÓN DE LA PÁGINA Y ESTILOS
# =================================================================
st.set_page_config(page_title="BioSim Pro | Destilación Flash", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    </style>
    """, unsafe_allow_html=True)

# =================================================================
# 2. LÓGICA DE SIMULACIÓN (ENCAPSULADA)
# =================================================================
def run_simulation(f_water, f_eth, t_feed, p_flash):
    # IMPORTANTE: Limpiar para evitar errores de IDs duplicados
    bst.main_flowsheet.clear()
    chemicals = tmo.Chemicals(["Water", "Ethanol"])
    bst.settings.set_thermo(chemicals)

    # Corrientes
    mosto = bst.Stream("mosto", Water=f_water, Ethanol=f_eth, units="kg/hr", T=t_feed + 273.15, P=101325)
    vinazas_retorno = bst.Stream("Vinazas_Retorno", Water=200, T=95+273.15, P=300000)

    # Equipos
    P100 = bst.Pump("P100", ins=mosto, P=4*101325)
    W210 = bst.HXprocess("W210", ins=(P100-0, vinazas_retorno), outs=("Mosto_Pre", "Drenaje"), phase0="l", phase1="l")
    W210.outs[0].T = 85 + 273.15
    
    W220 = bst.HXutility("W220", ins=W210-0, outs="Mezcla", T=92+273.15)
    V100 = bst.IsenthalpicValve("V100", ins=W220-0, outs="Mezcla_Bifasica", P=p_flash)
    
    # Manejo de error .duty: El Flash se define con Q=0 o V=fracción_vapor
    V1 = bst.Flash("V1", ins=V100-0, outs=("Vapor_caliente", "Vinazas"), P=p_flash, Q=0)
    
    W310 = bst.HXutility("W310", ins=V1-0, outs="Producto_Final", T=25+273.15)
    P200 = bst.Pump("P200", ins=V1-1, outs=vinazas_retorno, P=3*101325)

    sys = bst.System("eth_sys", path=(P100, W210, W220, V100, V1, W310, P200))
    sys.simulate()
    return sys

def generar_reportes(sistema):
    # Tabla Materia
    m_data = []
    for s in sistema.streams:
        if s.F_mass > 0.01:
            m_data.append({
                "ID": s.ID, "Temp (°C)": s.T-273.15, "Flujo (kg/h)": s.F_mass, 
                "Eth %": (s.imass['Ethanol']/s.F_mass)*100
            })
    
    # Tabla Energía (Corrigiendo acceso a duty y power)
    e_data = []
    for u in sistema.units:
        duty = getattr(u, 'duty', 0) / 3600 if hasattr(u, 'duty') else 0
        power = u.power_utility.rate if u.power_utility else 0
        if abs(duty) > 0.1 or power > 0.1:
            e_data.append({"Equipo": u.ID, "Calor (kW)": duty, "Potencia (kW)": power})
            
    return pd.DataFrame(m_data), pd.DataFrame(e_data)

# =================================================================
# 3. INTERFAZ DE USUARIO (LAYOUT)
# =================================================================
st.title("🧪 BioSim: Simulador de Purificación de Etanol")
st.subheader("Ingeniería de Procesos con IA")

# Sidebar para parámetros
with st.sidebar:
    st.header("⚙️ Configuración")
    f_w = st.slider("Flujo de Agua (kg/h)", 500, 2000, 900)
    f_e = st.slider("Flujo de Etanol (kg/h)", 10, 500, 100)
    p_f = st.number_input("Presión de Flash (Pa)", value=101325)
    
    st.divider()
    api_key = st.text_input("Gemini API Key", type="password")

# Layout de dos columnas principales
col_graf, col_res = st.columns([1, 1])

if st.button("🚀 Ejecutar Simulación"):
    with st.spinner("Simulando proceso..."):
        try:
            sys = run_simulation(f_w, f_e, 25, p_f)
            df_m, df_e = generar_reportes(sys)

            with col_graf:
                st.subheader("📈 Diagrama de Proceso (PFD)")
                # Renderizar diagrama usando Graphviz
                st.graphviz_chart(sys.diagram('dot'))
                
            with col_res:
                st.subheader("📋 Balances de Materia")
                st.dataframe(df_m.style.format(precision=2), use_container_width=True)
                
                st.subheader("⚡ Consumo Energético")
                st.dataframe(df_e.style.format(precision=2), use_container_width=True)

            # --- SECCIÓN IA ---
            st.divider()
            if api_key:
                st.subheader("🤖 Análisis del Tutor IA")
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel('gemini-2.5-pro')
                
                prompt = f"""
                Analiza como tutor de Ingeniería Química:
                Datos de corrientes: {df_m.to_string()}
                Datos de equipos: {df_e.to_string()}
                1. ¿Es buena la separación de etanol en el 'Producto_Final'?
                2. Sugiere un cambio térmico para mejorar la eficiencia.
                """
                response = model.generate_content(prompt)
                st.info(response.text)
            else:
                st.warning("Introduce tu API Key en el lateral para activar el Tutor IA.")

        except Exception as e:
            st.error(f"Error en la simulación: {e}")

else:
    st.info("Ajusta los parámetros en el panel lateral y pulsa 'Ejecutar Simulación'.")
