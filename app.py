import streamlit as st
import pandas as pd
from data_processor import DataProcessor
from polygon_generator import PolygonGenerator
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import json
import os
import time

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
except Exception as e:
    st.error(f"Ошибка инициализации: {str(e)}")
    st.stop()

# Заголовок
st.title("🗺️ Сервис генерации полигонов аудиторов")
st.markdown("---")

# Боковая панель
with st.sidebar:
    st.header("📊 Управление данными")
    
    # Загрузка файла с прогресс-баром
    uploaded_file = st.file_uploader(
        "Загрузите Excel файл с данными",
        type=['xlsx', 'xls'],
        help="Файл должен содержать колонки: ТП, Дата визита, Гео/ш, Гео/д"
    )
    
    if uploaded_file is not None:
        # Прогресс-бар
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        try:
            # Имитация прогресса
            status_text.text("Чтение файла...")
            progress_bar.progress(20)
            
            # Обработка файла
            count, message = data_processor.process_uploaded_file(uploaded_file)
            
            progress_bar.progress(80)
            status_text.text("Сохранение данных...")
            
            if count:
                progress_bar.progress(100)
                status_text.text("✅ Готово!")
                st.success(message)
                # Убираем st.rerun() и time.sleep()
            else:
                progress_bar.progress(100)
                status_text.text("❌ Ошибка!")
                st.error(message)
            
            # Убираем прогресс-бар
            progress_bar.empty()
            status_text.empty()
            
        except Exception as e:
            progress_bar.empty()
            status_text.empty()
            st.error(f"Ошибка при загрузке: {str(e)}")
    
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
        if st.button("🔄 Обновить", type="primary"):
            st.cache_data.clear()
            st.rerun()
    
    with col2:
        if st.button("🗑️ Очистить всё", type="secondary"):
            data_processor.clear_data()
            if 'file_processed' in st.session_state:
                del st.session_state.file_processed
            if 'polygons' in st.session_state:
                del st.session_state.polygons
            st.rerun()
    
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
tab1, tab2, tab3, tab4 = st.tabs(
    ["📋 Данные", "🗺️ Карта", "📐 Полигоны", "📥 Экспорт"]
)

with tab1:
    st.header("Просмотр данных")
    
    # Фильтр по аудитору
    auditors = data_processor.get_auditors()
    selected_auditor = st.selectbox(
        "Выберите аудитора",
        ["Все"] + auditors if auditors else ["Все"]
    )
    
    # Получение данных
    if selected_auditor == "Все":
        data_list = list(data_processor.data.values())
    else:
        data_list = data_processor.get_data_by_auditor(selected_auditor)
    
    if data_list:
        # Конвертация в DataFrame
        df = pd.DataFrame(data_list)
        
        # Фильтрация валидных координат
        if 'lat' in df.columns and 'lon' in df.columns:
            df['lat'] = pd.to_numeric(df['lat'], errors='coerce')
            df['lon'] = pd.to_numeric(df['lon'], errors='coerce')
            df = df.dropna(subset=['lat', 'lon'])
        
        if not df.empty:
            # Выбираем колонки для отображения
            display_cols = ['tp_id', 'auditor', 'city', 'visit_date', 'lat', 'lon']
            display_cols = [col for col in display_cols if col in df.columns]
            
            # Поиск по данным
            search = st.text_input("🔍 Поиск по ТП или городу", "")
            if search:
                mask = pd.Series(False, index=df.index)
                if 'tp_id' in df.columns:
                    mask = mask | df['tp_id'].str.contains(search, case=False, na=False)
                if 'city' in df.columns:
                    mask = mask | df['city'].str.contains(search, case=False, na=False)
                df = df[mask]
            
            # Отображение с пагинацией
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
    st.header("Визуализация на карте")
    
    if data_list:
        # Подготовка данных для карты
        df_map = pd.DataFrame(data_list)
        
        # Фильтр по аудитору
        selected_auditor_map = st.selectbox(
            "Выберите аудитора для карты",
            ["Все"] + auditors if auditors else ["Все"],
            key="map_auditor"
        )
        
        if selected_auditor_map != "Все":
            df_map = df_map[df_map['auditor'] == selected_auditor_map]
        
        # Проверка координат
        if not df_map.empty and 'lat' in df_map.columns and 'lon' in df_map.columns:
            df_map['lat'] = pd.to_numeric(df_map['lat'], errors='coerce')
            df_map['lon'] = pd.to_numeric(df_map['lon'], errors='coerce')
            df_map = df_map.dropna(subset=['lat', 'lon'])
        
        if not df_map.empty:
            try:
                # Создание карты
                fig = px.scatter_mapbox(
                    df_map,
                    lat='lat',
                    lon='lon',
                    color='auditor' if 'auditor' in df_map.columns else None,
                    hover_name='tp_id' if 'tp_id' in df_map.columns else None,
                    hover_data={
                        'city': True,
                        'visit_date': True,
                        'address': True
                    } if 'city' in df_map.columns else None,
                    zoom=10,
                    height=600,
                    title=f"Точки посещений (всего: {len(df_map)})"
                )
                
                fig.update_layout(
                    mapbox_style="open-street-map",
                    margin={"r": 0, "t": 30, "l": 0, "b": 0}
                )
                
                st.plotly_chart(fig, use_container_width=True)
            except Exception as e:
                st.error(f"Ошибка при создании карты: {str(e)}")
        else:
            st.warning("Нет данных с координатами для отображения на карте")
    else:
        st.info("Нет данных для отображения")

with tab3:
    st.header("Генерация полигонов")
    
    # Проверка наличия данных
    if not data_processor.data:
        st.warning("Нет данных для генерации полигонов. Сначала загрузите файл с данными.")
    else:
        if st.button("🚀 Создать полигоны для всех аудиторов", type="primary"):
            with st.spinner("Генерация полигонов..."):
                # Показываем прогресс
                status_text = st.empty()
                status_text.info("Начинаем генерацию полигонов...")
                
                polygons, errors = polygon_generator.create_polygons_for_all_auditors(
                    min_points=min_points,
                    buffer_km=buffer_km
                )
                
                status_text.empty()
                
                if polygons:
                    st.success(f"✅ Создано {len(polygons)} полигонов")
                    
                    # Информация о полигонах
                    st.subheader("Результаты")
                    
                    polygons_df = pd.DataFrame([
                        {
                            'Аудитор': p['auditor_id'],
                            'Количество точек': p['points_count'],
                            'Площадь (км²)': f"{p.get('area_km2', 0):.1f}"
                        }
                        for p in polygons
                    ])
                    st.dataframe(polygons_df, use_container_width=True)
                    
                    # Сохранение в сессию
                    st.session_state['polygons'] = polygons
                    
                    # Визуализация полигонов
                    if len(polygons) > 0:
                        st.subheader("Визуализация полигонов")
                        
                        all_coords = []
                        for p in polygons:
                            for lon, lat in p['coordinates']:
                                all_coords.append({
                                    'auditor': p['auditor_id'],
                                    'lon': lon,
                                    'lat': lat,
                                    'type': 'polygon'
                                })
                        
                        if all_coords:
                            df_poly = pd.DataFrame(all_coords)
                            
                            try:
                                fig = px.scatter_mapbox(
                                    df_poly,
                                    lat='lat',
                                    lon='lon',
                                    color='auditor',
                                    hover_data={'auditor': True},
                                    zoom=5,
                                    height=500,
                                    title="Визуализация полигонов"
                                )
                                
                                fig.update_layout(
                                    mapbox_style="open-street-map",
                                    margin={"r": 0, "t": 30, "l": 0, "b": 0}
                                )
                                
                                st.plotly_chart(fig, use_container_width=True)
                            except Exception as e:
                                st.error(f"Ошибка при визуализации: {str(e)}")
                    
                    if errors:
                        st.warning("⚠️ Ошибки при создании некоторых полигонов:")
                        for error in errors:
                            st.code(error)
                else:
                    st.error("❌ Не удалось создать ни одного полигона")
                    if errors:
                        for error in errors:
                            st.code(error)
    
    # Отображение сохраненных полигонов
    if 'polygons' in st.session_state and st.session_state['polygons']:
        st.markdown("---")
        st.subheader("💾 Сохраненные полигоны")
        
        for p in st.session_state['polygons']:
            with st.expander(f"🔷 {p['auditor_id']} ({p['points_count']} точек, {p.get('area_km2', 0):.1f} км²)"):
                st.write("Первые 5 точек полигона:")
                st.code(p['coordinates'][:5])

with tab4:
    st.header("📤 Экспорт данных")
    
    if 'polygons' in st.session_state and st.session_state['polygons']:
        # Экспорт в KML
        st.subheader("🗺️ Экспорт в KML")
        
        if st.button("📥 Создать KML"):
            with st.spinner("Создание KML файла..."):
                kml_file = polygon_generator.generate_kml(
                    st.session_state['polygons']
                )
                
                if kml_file and os.path.exists(kml_file):
                    with open(kml_file, 'rb') as f:
                        st.download_button(
                            label="Скачать KML файл",
                            data=f,
                            file_name=os.path.basename(kml_file),
                            mime="application/vnd.google-earth.kml+xml"
                        )
                else:
                    st.error(f"Ошибка при создании KML файла")
        
        # Экспорт в GeoJSON
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
        
        # Экспорт данных в CSV
        st.subheader("📊 Экспорт данных в CSV")
        
        if st.button("📥 Создать CSV"):
            with st.spinner("Создание CSV файла..."):
                df_export = pd.DataFrame(list(data_processor.data.values()))
                if not df_export.empty:
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
