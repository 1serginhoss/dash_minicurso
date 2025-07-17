import streamlit as st
import geemap.foliumap as geemap
import ee
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

# Inicialização do Earth Engine
try:
    ee.Initialize()
except Exception as e:
    try:
        ee.Authenticate()
        ee.Initialize()
    except:
        st.warning("Falha na autenticação do Earth Engine. Verifique suas credenciais.")

# Configuração da página
st.set_page_config(layout="wide", page_title="Monitoramento da Bacia do Rio Pericumã")
st.title("🌊 Monitoramento da Superfície de Água")
st.subheader("Bacia Hidrográfica do Rio Pericumã")

# Carregar a bacia hidrográfica do Earth Engine Assets
@st.cache_resource
def load_bacia_from_gee():
    try:
        # Carrega a bacia do seu Earth Engine Assets
        bacia = ee.FeatureCollection('projects/ee-serginss/assets/Bacia_Pericuma_ZEE_v2')
        
        # Verifica se a coleção não está vazia
        size = bacia.size().getInfo()
        if size == 0:
            st.error("A coleção de features está vazia")
            return None, None
            
        # Pega a primeira feature e sua geometria
        first_feature = ee.Feature(bacia.first())
        geometry = first_feature.geometry()
        
        # Verifica se a geometria é válida
        if geometry.isEmpty().getInfo():
            st.error("Geometria vazia na feature")
            return None, None
            
        # Obtém propriedades (nome da bacia)
        properties = first_feature.getInfo().get('properties', {})
        area_name = properties.get('nome', 'Bacia do Rio Pericumã')
        
        return geometry, area_name
        
    except Exception as e:
        st.error(f"Erro ao carregar a bacia do GEE: {str(e)}")
        return None, None

# Carregar a geometria da bacia
geometry, area_name = load_bacia_from_gee()
if geometry:
    st.success(f"Área de estudo carregada: {area_name}")

# Configurações dos dados do MapBiomas Água
DATA_CONFIG = {
    'cobertura_agua_anual': {
        'asset': 'projects/mapbiomas-public/assets/brazil/water/collection3/mapbiomas_water_annual_water_coverage_v1',
        'palette': ['#ffffff', '#0101c1'],
        'years': list(range(1985, 2024)),
        'band_prefix': 'annual_water_coverage_'
    },
    'frequencia_agua': {
        'asset': 'projects/mapbiomas-public/assets/brazil/water/collection3/mapbiomas_water_frequency_v1',
        'palette': ['#e5e5ff', '#ccccff', '#b2b2ff', '#9999ff', '#7f7fff', 
                   '#6666ff', '#4c4cff', '#3232ff', '#1919ff', '#0000ff'],
        'years': ['1985_2023'],
        'band_prefix': 'water_frequency_'
    }
}

# Carregar os dados do MapBiomas Água
@st.cache_resource
def load_data(data_type):
    return ee.Image(DATA_CONFIG[data_type]['asset'])

# Sidebar - Controles
with st.sidebar:
    st.header("Configurações")
    
    data_type = st.selectbox(
        "Tipo de análise",
        options=list(DATA_CONFIG.keys()),
        format_func=lambda x: "Cobertura Anual" if x == "cobertura_agua_anual" else "Frequência"
    )
    
    if data_type == "cobertura_agua_anual":
        selected_years = st.multiselect(
            "Selecione os anos",
            options=DATA_CONFIG[data_type]['years'],
            default=[2023, 2020, 2015, 2010, 2005, 2000]
        )
    else:
        selected_years = DATA_CONFIG[data_type]['years']
    
    buffer_distance = st.select_slider(
        "Buffer (km)",
        options=[0, 1, 2, 3, 4, 5],
        value=0
    )
    
    show_basin = st.checkbox("Mostrar limites da bacia", value=True)
    opacity = st.slider("Opacidade das camadas", 0.1, 1.0, 0.7)

# Carregar os dados do MapBiomas
image = load_data(data_type)

# Aplicar buffer se necessário
if buffer_distance > 0 and geometry:
    study_area = geometry.buffer(buffer_distance * 1000)
elif geometry:
    study_area = geometry
else:
    study_area = None

# Mapa interativo
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("Visualização Espacial")
    m = geemap.Map(zoom=9)
    
    if geometry:
        m.centerObject(ee.FeatureCollection(ee.Feature(geometry)), 9)
    
    if show_basin and geometry:
        m.addLayer(ee.FeatureCollection(ee.Feature(geometry)).style(**{'color': 'yellow', 'fillColor': '00000000'}), {}, "Limites da Bacia")
    
    if study_area and data_type == "cobertura_agua_anual":
        for year in selected_years:
            band_name = f"{DATA_CONFIG[data_type]['band_prefix']}{year}"
            water_layer = image.select(band_name).clip(study_area)
            
            m.addLayer(
                water_layer,
                {'min': 0, 'max': 1, 'palette': DATA_CONFIG[data_type]['palette']},
                f"Água {year}",
                opacity=opacity
            )
    elif study_area and data_type == "frequencia_agua":
        band_name = f"{DATA_CONFIG[data_type]['band_prefix']}{selected_years[0]}"
        freq_layer = image.select(band_name).clip(study_area)
        
        m.addLayer(
            freq_layer,
            {'min': 1, 'max': 36, 'palette': DATA_CONFIG[data_type]['palette']},
            "Frequência de Água 1985-2023",
            opacity=opacity
        )
    
    m.addLayerControl()
    m.to_streamlit(height=600)

# Cálculo de estatísticas (apenas se a geometria foi carregada)
if geometry:
    with col2:
        st.subheader(f"Análise Temporal - {area_name}")
        
        if data_type == "cobertura_agua_anual":
            with st.spinner("Calculando séries temporais..."):
                # Função para calcular área por ano
                def calculate_area(year):
                    band_name = f"{DATA_CONFIG[data_type]['band_prefix']}{year}"
                    water_mask = image.select(band_name)
                    
                    area_stats = water_mask.multiply(ee.Image.pixelArea()) \
                        .reduceRegion(
                            reducer=ee.Reducer.sum(),
                            geometry=study_area,
                            scale=30,
                            maxPixels=1e13
                        ).getInfo()
                    
                    water_area = area_stats.get(band_name, 0) / 1e6  # Convert to km²
                    return {'Ano': year, 'Área (km²)': round(water_area, 2)}
                
                # Calcular para todos os anos
                stats_data = [calculate_area(year) for year in DATA_CONFIG[data_type]['years']]
                df = pd.DataFrame(stats_data)
                
                # Gráfico de evolução
                fig = px.line(
                    df, 
                    x="Ano", 
                    y="Área (km²)",
                    markers=True,
                    title=f"Evolução da Superfície de Água - {area_name}",
                    template="plotly_white"
                )
                
                # Adicionar linha de tendência
                z = np.polyfit(df['Ano'], df['Área (km²)'], 1)
                p = np.poly1d(z)
                df['Tendência'] = p(df['Ano'])
                
                fig.add_trace(
                    go.Scatter(
                        x=df['Ano'],
                        y=df['Tendência'],
                        name='Tendência',
                        line=dict(color='red', dash='dash')
                    )
                )
                
                fig.update_layout(
                    hovermode="x unified",
                    xaxis_title="Ano",
                    yaxis_title="Área de Água (km²)",
                    height=400
                )
                
                st.plotly_chart(fig, use_container_width=True)
                
                # Tabela de dados
                st.dataframe(
                    df.style.format({"Área (km²)": "{:.2f}"})
                     .highlight_max(subset=["Área (km²)"], color='lightgreen')
                     .highlight_min(subset=["Área (km²)"], color='#ffcccb')
                )
                
                # Botão de download
                csv = df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Download dos dados",
                    data=csv,
                    file_name=f"area_agua_{area_name.lower().replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime='text/csv'
                )
        else:
            st.info("""
            **Análise de Frequência (1985-2023)**
            
            Mostra com que frequência cada pixel foi classificado como água no período.
            - Valores próximos a 1: água esporádica
            - Valores próximos a 36: água permanente
            """)

# Informações adicionais
st.expander("ℹ️ Sobre este dashboard").write(f"""
Este dashboard monitora a superfície de água na {area_name} utilizando dados do MapBiomas Água Collection 3.

**Funcionalidades:**
- Visualização da cobertura anual de água (1985-2023)
- Análise de frequência de água (permanência)
- Série temporal da área de água
- Opção de buffer para análise da área entorno

**Dados utilizados:**
- [MapBiomas Água Collection 3](https://mapbiomas.org/)
- Bacia hidrográfica carregada de: `projects/ee-serginss/assets/Bacia_Pericuma_ZEE_v2`

Desenvolvido por LAGEOS/LAB - Universidade Estadual do Maranhão
""")