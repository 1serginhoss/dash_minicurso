import streamlit as st 
import geemap.foliumap as geemap
import ee
import json
import pandas as pd
from plotly.subplots import make_subplots
import plotly.graph_objects as go
from scipy import stats

# Inicializar Earth Engine
try:
    ee.Initialize(project='ee-serginss-459118')
except Exception:
    ee.Authenticate()
    ee.Initialize(project='ee-serginss-459118')

# Configuração da página
st.set_page_config(layout='wide', page_title="Monitoramento BHRP", page_icon="💧")
st.title("Monitoramento da Bacia Hidrográfica do Rio Pericumã - MapBiomas Água")

# CSS para os cards
st.markdown("""
<style>
    .metric-card {
        border-radius: 10px;
        padding: 15px;
        background-color: white;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        margin-bottom: 20px;
    }
    .metric-title { font-size: 16px; color: #555; margin-bottom: 5px; }
    .metric-value { font-size: 24px; font-weight: bold; color: #2532e4; }
    .metric-change { font-size: 14px; color: #666; }
    .positive {color: #2ecc71;}
    .negative {color: #e74c3c;}
</style>
""", unsafe_allow_html=True)

# --- Carregar a geometria da bacia hidrográfica ---
@st.cache_resource
def load_bacia_geometry():
    with open('assets/bacia_pericuma_OF.geojson', 'r', encoding='utf-8') as f:
        geojson_data = json.load(f)
        geometry = geojson_data['features'][0]['geometry']
        return ee.Geometry(geometry)

geometry = load_bacia_geometry()

# Seleção de anos
anos = list(range(1985, 2024))
anos_selecionados = st.multiselect(
    "Selecione o(s) ano(s) para análise:",
    anos,
    default=[1985, 1995, 2005, 2015, 2023]
)

# Imagem do MapBiomas
mapbiomas = ee.Image("projects/mapbiomas-public/assets/brazil/lulc/collection9/mapbiomas_collection90_integration_v1")
image_clip = mapbiomas.clip(geometry)

# Mapa interativo
st.subheader("🗺️ Mapa Interativo - Água na BHRP")
with st.expander("Clique para expandir o mapa", expanded=True):
    m = geemap.Map(center=[-2.5, -45], zoom=7)
    m.addLayer(ee.FeatureCollection([ee.Feature(geometry)]), {"color": "red", "fillColor": "00000000"}, "Bacia Pericumã")

    for ano in sorted(anos_selecionados):
        banda = image_clip.select(f"classification_{ano}")
        agua = banda.eq(33).selfMask()
        m.addLayer(agua, {"palette": ["#2532e4"], "opacity": 0.7}, f"Água {ano}")

    m.addLayerControl()
    m.to_streamlit(height=500)

# Cálculo da área de água
@st.cache_data
def calcular_areas_temporais(_geometry):
    dados = []
    for ano in range(1985, 2024):
        banda = image_clip.select(f"classification_{ano}")
        agua = banda.eq(33)
        area_m2 = agua.multiply(ee.Image.pixelArea()).reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=_geometry,
            scale=30,
            maxPixels=1e13
        ).getInfo()
        area_km2 = area_m2.get(f"classification_{ano}", 0) / 1e6
        dados.append({"Ano": ano, "Área (km²)": round(area_km2, 2)})
    return pd.DataFrame(dados)

df_completo = calcular_areas_temporais(geometry)
df_selecionados = df_completo[df_completo['Ano'].isin(anos_selecionados)]

# Cálculo de métricas
if len(anos_selecionados) >= 2:
    a_ini = df_selecionados.iloc[0]['Área (km²)']
    a_fim = df_selecionados.iloc[-1]['Área (km²)']
    var_abs = a_fim - a_ini
    var_pct = (var_abs / a_ini) * 100 if a_ini != 0 else 0

    x = df_completo['Ano'].values
    y = df_completo['Área (km²)'].values
    slope, intercept, r_value, _, _ = stats.linregress(x, y)
    trend_km2_ano = slope
    trend_pct_ano = (slope / y.mean()) * 100 if y.mean() != 0 else 0

# Cards de Métricas
if len(anos_selecionados) >= 2:
    st.subheader("📊 Métricas de Variação")
    cols = st.columns(4)
    with cols[0]:
        st.markdown(f"""<div class="metric-card"><div class="metric-title">Área Inicial ({anos_selecionados[0]})</div><div class="metric-value">{a_ini:.2f} km²</div></div>""", unsafe_allow_html=True)
    with cols[1]:
        st.markdown(f"""<div class="metric-card"><div class="metric-title">Área Final ({anos_selecionados[-1]})</div><div class="metric-value">{a_fim:.2f} km²</div></div>""", unsafe_allow_html=True)
    with cols[2]:
        change_class = "positive" if var_abs >= 0 else "negative"
        icon = "↑" if var_abs >= 0 else "↓"
        st.markdown(f"""<div class="metric-card"><div class="metric-title">Variação Absoluta</div><div class="metric-value">{var_abs:.2f} km²</div><div class="metric-change {change_class}">{icon} {abs(var_pct):.1f}%</div></div>""", unsafe_allow_html=True)
    with cols[3]:
        trend_class = "positive" if trend_km2_ano >= 0 else "negative"
        icon2 = "↑" if trend_km2_ano >= 0 else "↓"
        st.markdown(f"""<div class="metric-card"><div class="metric-title">Tendência (1985-2023)</div><div class="metric-value">{trend_km2_ano:.3f} km²/ano</div><div class="metric-change {trend_class}">{icon2} {trend_pct_ano:.2f}%/ano</div></div>""", unsafe_allow_html=True)

# Gráfico temporal
st.subheader("📈 Série Temporal da Área de Água na BHRP")
fig = make_subplots()
fig.add_trace(go.Scatter(
    x=df_completo['Ano'],
    y=df_completo['Área (km²)'],
    mode='lines',
    name='Área de Água',
    line=dict(color='#2532e4', width=3)
))
fig.add_trace(go.Scatter(
    x=df_selecionados['Ano'],
    y=df_selecionados['Área (km²)'],
    mode='markers+text',
    name='Anos Selecionados',
    marker=dict(color='red', size=10),
    text=df_selecionados['Área (km²)'].round(2).astype(str) + ' km²',
    textposition='top center'
))
fig.add_trace(go.Scatter(
    x=df_completo['Ano'],
    y=intercept + slope * df_completo['Ano'],
    mode='lines',
    name='Tendência Linear',
    line=dict(color='orange', dash='dash')
))
fig.update_layout(
    title="Variação da Área de Água - Bacia do Rio Pericumã (1985-2023)",
    xaxis_title="Ano",
    yaxis_title="Área (km²)",
    template="plotly_white",
    hovermode="x unified",
    height=500
)
st.plotly_chart(fig, use_container_width=True)

# Tabela com dados
st.subheader("📋 Tabela de Áreas Anuais - BHRP")
df_show = df_completo.copy()
df_show['Variação Anual (km²)'] = df_show['Área (km²)'].diff()
df_show['Variação Anual (%)'] = df_show['Área (km²)'].pct_change() * 100
df_show['Variação Acumulada (%)'] = (df_show['Área (km²)'] / df_show['Área (km²)'].iloc[0] - 1) * 100
df_show = df_show.round(2)

st.dataframe(df_show, use_container_width=True)

st.download_button(
    label="📥 Baixar CSV",
    data=df_show.to_csv(index=False).encode('utf-8'),
    file_name="bhrp_area_agua_1985_2023.csv",
    mime='text/csv'
)
