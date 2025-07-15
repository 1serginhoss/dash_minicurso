import streamlit as st
import geemap.foliumap as geemap
import ee
import json
import pandas as pd
import geopandas as gpd
import tempfile
import os
import plotly.express as px
import matplotlib.pyplot as plt

# Inicialização do Earth Engine
try:
    ee.Initialize(project='ee-serginss-459118')
except Exception as e:
    try:
        ee.Authenticate()
        ee.Initialize(project='ee-serginss-459118')
    except:
        st.warning("Falha na autenticação do Earth Engine. Verifique suas credenciais.")

# Configuração da página
st.set_page_config(layout='wide')
st.title("🌱 APP MAPBIOMAS LAGEOS/LAB - MARANHÃO")
st.write("Análise de cobertura do solo para municípios do Maranhão usando MapBiomas Collection 9")

# Carregar GeoJSON com municípios
try:
    with open('assets/municipios_ma.geojson', 'r', encoding='utf-8') as f:
        geojson_data = json.load(f)
        st.success("Arquivo GeoJSON carregado com sucesso!")
except Exception as e:
    st.error(f"Erro ao carregar GeoJSON: {str(e)}")
    geojson_data = None

@st.cache_resource
def load_municipios():
    municipios = {}
    if geojson_data:
        for feature in geojson_data['features']:
            nome = feature['properties'].get('NM_MUNICIP')
            if nome:
                municipios[nome] = feature['geometry']
    return municipios

MUNICIPIOS_MA = load_municipios()

mapbiomas_image = ee.Image('projects/mapbiomas-public/assets/brazil/lulc/collection9/mapbiomas_collection90_integration_v1')

CLASS_CONFIG = {
    'codes': [1, 3, 4, 5, 6, 49, 10, 11, 12, 32, 29, 50, 14, 15, 18, 19, 39, 20, 40, 62, 41, 36, 46, 47, 35, 48, 9, 21, 22, 23, 24, 30, 25, 26, 33, 31, 27],
    'new_classes': [1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 4, 4, 4, 4, 4, 5, 5, 5, 6],
    'palette': ["#1f8d49", "#d6bc74", "#ffefc3", "#d4271e", "#2532e4", "#ffffff"],
    'names': {
        1: "Formação Florestal", 
        2: "Formação Campestre", 
        3: "Agricultura", 
        4: "Área Urbana", 
        5: "Corpo D'água", 
        6: "Não observado"
    }
}

def reclassify_bands(image, codes, new_classes):
    remapped_bands = []
    for year in range(1985, 2024):
        original_band = f'classification_{year}'
        remapped_band = image.select(original_band).remap(codes, new_classes).rename(original_band)
        remapped_bands.append(remapped_band)
    return ee.Image.cat(remapped_bands)

remapped_image = reclassify_bands(mapbiomas_image, CLASS_CONFIG['codes'], CLASS_CONFIG['new_classes'])

years = list(range(1985, 2024))
selected_years = st.multiselect('Selecione o(s) ano(s)', years, default=[2023])

geometry = None
area_name = "Área Carregada"

with st.expander('Defina a área de estudo', expanded=True):
    tab1, tab2, tab3 = st.tabs(["Selecionar Município", "Upload Shapefile", "Inserir GeoJSON"])
    with tab1:
        if MUNICIPIOS_MA:
            municipio = st.selectbox("Selecione um município do Maranhão", options=sorted(MUNICIPIOS_MA.keys()), index=0)
        else:
            st.warning("Nenhum município carregado. Verifique o arquivo municipios_ma.geojson")
            municipio = None
    with tab2:
        uploaded_files = st.file_uploader("Faça upload dos arquivos do Shapefile (.shp, .dbf, .shx)", type=['shp', 'dbf', 'shx'], accept_multiple_files=True)
    with tab3:
        geometry_input = st.text_area("Cole seu GeoJSON aqui")

if uploaded_files:
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            for file in uploaded_files:
                file_path = os.path.join(temp_dir, file.name)
                with open(file_path, "wb") as f:
                    f.write(file.getbuffer())
            shp_files = [f for f in os.listdir(temp_dir) if f.endswith('.shp')]
            if shp_files:
                gdf = gpd.read_file(os.path.join(temp_dir, shp_files[0]))
                geojson = json.loads(gdf.to_json())
                geometry = ee.Geometry(geojson['features'][0]['geometry'])
                area_name = geojson['features'][0]['properties'].get('name', 'Área Carregada')
                st.success("Shapefile carregado com sucesso!")
            else:
                st.error("Nenhum arquivo .shp encontrado nos arquivos enviados.")
    except Exception as e:
        st.error(f"Erro ao processar Shapefile: {str(e)}")
elif geometry_input.strip():
    try:
        geo_data = json.loads(geometry_input)
        if 'geometry' in geo_data:
            geometry = ee.Geometry(geo_data['geometry'])
        else:
            geometry = ee.Geometry(geo_data)
        st.success("GeoJSON carregado com sucesso!")
    except Exception as e:
        st.error(f'Erro no GeoJSON: {str(e)}')
elif municipio and municipio in MUNICIPIOS_MA:
    geometry = ee.Geometry(MUNICIPIOS_MA[municipio])
    area_name = municipio
    st.success(f"Município {municipio} carregado com sucesso!")

m = geemap.Map(center=[-5, -45], zoom=6, plugin_Draw=True)
if geometry:
    study_area = ee.FeatureCollection([ee.Feature(geometry)])
    m.centerObject(study_area, zoom=9)
    m.addLayer(study_area, {'color': 'red', 'width': 2}, 'Área de estudo')
    remapped_image = remapped_image.clip(geometry)

for year in selected_years:
    selected_band = f"classification_{year}"
    m.addLayer(
        remapped_image.select(selected_band),
        {
            'palette': CLASS_CONFIG['palette'],
            'min': 1,
            'max': 6
        },
        f"Classificação {year}"
    )

m.to_streamlit(height=600)

if geometry and selected_years:
    st.subheader(f"📊 ESTATÍSTICAS DE ÁREA POR CLASSE - {area_name.upper()}")
    with st.spinner('Calculando estatísticas...'):
        stats_data = []
        for year in selected_years:
            band = remapped_image.select(f"classification_{year}")
            class_masks = [band.eq(i).rename(f'class_{i}') for i in [1, 2, 3, 4, 5, 6]]
            areas = ee.Image.cat(*class_masks).multiply(ee.Image.pixelArea()).reduceRegion(
                reducer=ee.Reducer.sum().repeat(6),
                geometry=geometry,
                scale=30,
                maxPixels=1e13
            )
            try:
                areas_dict = areas.getInfo()
                if 'sum' in areas_dict:
                    areas_list = areas_dict['sum']
                    for i, class_value in enumerate([1, 2, 3, 4, 5, 6]):
                        area_m2 = areas_list[i] if i < len(areas_list) else 0
                        area_km2 = area_m2 / 1e6
                        stats_data.append({
                            "Ano": year,
                            "Classe": class_value,
                            "Nome da Classe": CLASS_CONFIG['names'][class_value],
                            "Área (km²)": round(area_km2, 2)
                        })
            except Exception as e:
                st.error(f"Erro ao processar {year}: {str(e)}")
                continue

    if not stats_data:
        st.warning("Nenhum dado encontrado para os parâmetros selecionados.")
        st.stop()

    df = pd.DataFrame(stats_data)

    # Gráfico 100% empilhado horizontal
    pivot_df = df.pivot(index="Ano", columns="Nome da Classe", values="Área (km²)").fillna(0)
    pivot_percent = pivot_df.div(pivot_df.sum(axis=1), axis=0) * 100

    class_order = ["Formação Florestal", "Formação Campestre", "Agricultura", 
                   "Área Urbana", "Corpo D'água", "Não observado"]
    custom_colors = {
        "Formação Florestal": "#1f8d49",
        "Formação Campestre": "#d6bc74",
        "Agricultura": "#ffefc3",
        "Área Urbana": "#d4271e",
        "Corpo D'água": "#2532e4",
        "Não observado": "#cccccc"
    }
    ordered_colors = [custom_colors.get(classe, "#cccccc") for classe in class_order]

    st.subheader("📊 DISTRIBUIÇÃO 100% EMPILHADA DAS CLASSES")
    fig, ax = plt.subplots(figsize=(15, 8))
    pivot_percent[class_order].plot(kind="barh", stacked=True, color=ordered_colors, ax=ax, edgecolor='white')
    ax.set_xlabel("Porcentagem (%)")
    ax.set_ylabel("Ano")
    ax.set_title("Distribuição das Áreas por Classe ao Longo dos Anos")
    ax.legend(title='Classes', bbox_to_anchor=(1.05, 1), loc='upper left')
    plt.tight_layout()
    st.pyplot(fig)

    st.subheader("🍕 DISTRIBUIÇÃO PERCENTUAL POR CLASSE")
    selected_year = st.selectbox("Selecione o ano para análise:", sorted(selected_years, reverse=True), index=0)
    year_df = df[df['Ano'] == selected_year]
    total_area = year_df['Área (km²)'].sum()
    year_df['Porcentagem'] = (year_df['Área (km²)'] / total_area) * 100
    pie_fig = px.pie(
        year_df,
        names="Nome da Classe",
        values="Porcentagem",
        title=f"Distribuição Percentual {selected_year}",
        color="Nome da Classe",
        color_discrete_map=custom_colors,
        hole=0.4,
        height=500
    )
    pie_fig.update_traces(
        textposition='inside',
        textinfo='percent+label',
        hovertemplate="<b>%{label}</b><br>%{percent:.1f}%<br>Área: %{value:.2f} km²",
        marker=dict(line=dict(color='white', width=1))
    )
    st.plotly_chart(pie_fig, use_container_width=True)

    st.subheader("📋 TABELA DE DADOS COMPLETA")
    st.dataframe(
        df.pivot(index='Ano', columns='Nome da Classe', values='Área (km²)')
        .style.format("{:.2f}")
        .set_properties(**{'background-color': '#f8f9fa', 'border': '1px solid #dee2e6'})
        .highlight_max(axis=0, color='#d4edda')
        .highlight_min(axis=0, color='#f8d7da')
    )
