import streamlit as st
import pandas as pd
from data_processor import DataProcessor
from polygon_generator import PolygonGenerator
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import json
import os

# Настройка страницы
st.set_page_config(
    page_title="Сервис полигонов аудиторов",
    page_icon="🗺️",
    layout="wide"
)

# Инициализация
@st.cache_resource
def init_processors():
    dp = DataProcessor()
    pg = PolygonGenerator(dp)
    return dp, pg

try:
    data_processor, polygon_generator = init_processors()
    # Данные уже загружены в __init__, ничего дополнительно не делаем
except Exception as e:
    st.error(f"Ошибка инициализации: {str(e)}")
    st.stop()

# Заголовок
st.title("🗺️ Сервис генерации полигонов аудиторов")
st.markdown("---")

# Боковая панель
with st.sidebar:
    st.header("📊 Управление данными")
    
    # Загрузка файла с защитой от повторной обработки
    uploaded_file = st.file_uploader(
        "Загрузите Excel файл с данными",
        type=['xlsx', 'xls'],
        help="Файл должен содержать колонки: ТП, Дата визита, Гео/ш, Гео/д"
    )
    
    if uploaded_file is not None:
        if ('file_processed' not in st.session_state or 
            st.session_state.file_processed != uploaded_file.name):
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            try:
                status_text.text("Чтение файла...")
                progress_bar.progress(20)
                
                count, message = data_processor.process_uploaded_file(uploaded_file)
                
                progress_bar.progress(80)
                status_text.text("Сохранение данных...")
                
                if count:
                    progress_bar.progress(100)
                    status_text.text("✅ Готово!")
                    st.success(message)
                    st.session_state.file_processed = uploaded_file.name
                else:
                    progress_bar.progress(100)
                    status_text.text("❌ Ошибка!")
                    st.error(message)
                
                progress_bar.empty()
                status_text.empty()
                
            except Exception as e:
                progress_bar.empty()
                status_text.empty()
                st.error(f"Ошибка при загрузке: {str(e)}")
        else:
            st.success(f"✅ Файл '{uploaded_file.name}' уже загружен")
    
    st.markdown("---")
    
    # Статистика
    st.header("📈 Статистика")
    try:
        stats = data_processor.get_statistics()
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Всего визитов", stats['total_visits'])
            st.metric("Городов", stats['cities'])
        with col2:
            st.metric("Аудиторов", stats['total_auditors'])
            st.metric("Регионов", stats['regions'])
    except Exception as e:
        st.error(f"Ошибка получения статистики: {str(e)}")
    
    st.markdown("---")
    
    # Действия с данными
    st.header("⚙️ Действия")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("💾 Сохранить данные", type="primary"):
            success, message = data_processor.save_data()
            if success:
                data_processor.data = data_processor.load_data()
                st.success(message)
            else:
                st.error(message)
    
    with col2:
        if st.button("🗑️ Очистить всё", type="secondary"):
            data_processor.clear_data()
            if 'file_processed' in st.session_state:
                del st.session_state.file_processed
            if 'polygons' in st.session_state:
                del st.session_state.polygons
            st.success("✅ Данные очищены")
    
    # Параметры генерации
    st.markdown("---")
    st.header("🔧 Параметры полигонов")
    
    min_points = st.slider(
        "Минимальное количество точек",
        min_value=3,
        max_value=20,
        value=3
    )
    
    buffer_km = st.slider(
        "Размер буфера (км)",
        min_value=0.0,
        max_value=5.0,
        value=0.5,
        step=0.1
    )

# Основная область
tab1, tab2, tab3 = st.tabs(
    ["📋 Данные", "📐 Полигоны", "📥 Экспорт"]
)

with tab1:
    st.header("Просмотр данных")
    
    auditors = data_processor.get_auditors()
    selected_auditor = st.selectbox(
        "Выберите аудитора",
        ["Все"] + auditors if auditors else ["Все"]
    )
    
    if selected_auditor == "Все":
        data_list = list(data_processor.data.values())
    else:
        data_list = data_processor.get_data_by_auditor(selected_auditor)
    
    if data_list:
        df = pd.DataFrame(data_list)
        
        if 'lat' in df.columns and 'lon' in df.columns:
            df['lat'] = pd.to_numeric(df['lat'], errors='coerce')
            df['lon'] = pd.to_numeric(df['lon'], errors='coerce')
            df = df.dropna(subset=['lat', 'lon'])
        
        if not df.empty:
            display_cols = ['tp_id', 'auditor', 'city', 'visit_date', 'lat', 'lon']
            display_cols = [col for col in display_cols if col in df.columns]
            
            search = st.text_input("🔍 Поиск по ТП или городу", "")
            if search:
                mask = pd.Series(False, index=df.index)
                if 'tp_id' in df.columns:
                    mask = mask | df['tp_id'].str.contains(search, case=False, na=False)
                if 'city' in df.columns:
                    mask = mask | df['city'].str.contains(search, case=False, na=False)
                df = df[mask]
            
            page_size = 50
            total_records = len(df)
            total_pages = max(1, (total_records + page_size - 1) // page_size)
            
            if total_pages > 1:
                page = st.number_input(
                    f"Страница (всего {total_pages})", 
                    min_value=1, 
                    max_value=total_pages, 
                    value=1
                )
                start_idx = (page - 1) * page_size
                end_idx = min(start_idx + page_size, total_records)
                df_display = df.iloc[start_idx:end_idx]
                st.caption(f"Показано {start_idx + 1}-{end_idx} из {total_records} записей")
            else:
                df_display = df
                st.caption(f"Всего записей: {total_records}")
            
            st.dataframe(
                df_display[display_cols],
                use_container_width=True,
                height=400
            )
        else:
            st.info("Нет данных с валидными координатами")
    else:
        st.info("Нет данных для отображения. Загрузите файл с данными.")

with tab2:
    st.header("Генерация полигонов")
    
    if not data_processor.data:
        st.warning("Нет данных для генерации полигонов. Сначала загрузите файл с данными.")
    else:
        if st.button("🚀 Создать полигоны для всех аудиторов", type="primary"):
            with st.spinner("Генерация полигонов..."):
                polygons, errors = polygon_generator.create_polygons_for_all_auditors(
                    min_points=min_points,
                    buffer_km=buffer_km
                )
                
                if polygons:
                    st.success(f"✅ Создано {len(polygons)} полигонов")
                    
                    st.subheader("Результаты")
                    
                    # Таблица с кнопкой скачивания в каждой строке
                    for idx, p in enumerate(polygons):
                        col1, col2, col3, col4 = st.columns([2, 1.5, 1.5, 1.5])
                        
                        with col1:
                            st.write(p['auditor_id'])
                        with col2:
                            st.write(p['points_count'])
                        with col3:
                            st.write(f"{p.get('area_km2', 0):.1f}")
                        with col4:
                            if st.button("📥 KML", key=f"kml_{p['auditor_id']}_{idx}"):
                                kml_file = polygon_generator.generate_kml([p])
                                if kml_file and os.path.exists(kml_file):
                                    with open(kml_file, 'rb') as f:
                                        st.download_button(
                                            label="Скачать",
                                            data=f,
                                            file_name=f"{p['auditor_id']}_{datetime.now().strftime('%Y%m%d')}.kml",
                                            mime="application/vnd.google-earth.kml+xml",
                                            key=f"download_{p['auditor_id']}_{idx}"
                                        )
                                else:
                                    st.error(f"Ошибка создания KML для {p['auditor_id']}")
                    
                    st.session_state['polygons'] = polygons
                    
                    if errors:
                        st.warning("⚠️ Ошибки при создании некоторых полигонов:")
                        for error in errors:
                            st.code(error)
                else:
                    st.error("❌ Не удалось создать ни одного полигона")
                    if errors:
                        for error in errors:
                            st.code(error)

with tab3:
    st.header("📤 Экспорт данных")
    
    if 'polygons' in st.session_state and st.session_state['polygons']:
        st.subheader("🗺️ Экспорт в KML")
        
        if st.button("📥 Создать общий KML"):
            with st.spinner("Создание KML файла..."):
                kml_file = polygon_generator.generate_kml(
                    st.session_state['polygons']
                )
                
                if kml_file and os.path.exists(kml_file):
                    with open(kml_file, 'rb') as f:
                        st.download_button(
                            label="Скачать общий KML файл",
                            data=f,
                            file_name=os.path.basename(kml_file),
                            mime="application/vnd.google-earth.kml+xml"
                        )
                else:
                    st.error("Ошибка при создании KML файла")
        
        st.subheader("🌐 Экспорт в GeoJSON")
        
        if st.button("📥 Создать GeoJSON"):
            with st.spinner("Создание GeoJSON файла..."):
                geojson_file = polygon_generator.export_to_geojson(
                    st.session_state['polygons']
                )
                
                if geojson_file and os.path.exists(geojson_file):
                    with open(geojson_file, 'rb') as f:
                        st.download_button(
                            label="Скачать GeoJSON",
                            data=f,
                            file_name=os.path.basename(geojson_file),
                            mime="application/json"
                        )
                else:
                    st.error("Ошибка при создании GeoJSON файла")
        
        st.subheader("📊 Экспорт данных в CSV")
                
        if st.button("📥 Создать CSV"):
            with st.spinner("Создание CSV файла..."):
                df_export = pd.DataFrame(list(data_processor.data.values()))
                if not df_export.empty:
                    # Меняем местами lat и lon
                    if 'lat' in df_export.columns and 'lon' in df_export.columns:
                        df_export['lat'], df_export['lon'] = df_export['lon'], df_export['lat']
                    
                    csv = df_export.to_csv(index=False)
                    
                    st.download_button(
                        label="Скачать CSV",
                        data=csv,
                        file_name=f"auditor_data_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv"
                    )
    else:
        st.info("Сначала создайте полигоны в разделе '📐 Полигоны'")

# Footer
st.markdown("---")
st.caption("🚀 Сервис разработан для генерации полигонов аудиторов на основе данных посещений")
