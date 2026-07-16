import streamlit as st
import pandas as pd
from data_processor import DataProcessor
from polygon_generator import PolygonGenerator
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import json
import os
import time

# Настройка страницы
st.set_page_config(
    page_title="Сервис полигонов аудиторов",
    page_icon="🗺️",
    layout="wide"
)

# Инициализация сессии
if 'initialized' not in st.session_state:
    st.session_state.initialized = True
    st.session_state.processed_files = {}
    st.session_state.polygons = []
    st.session_state.last_update = None
    st.session_state.data_loaded = False

@st.cache_resource
def init_processors():
    try:
        dp = DataProcessor()
        pg = PolygonGenerator(dp)
        return dp, pg
    except Exception as e:
        st.error(f"❌ Ошибка инициализации: {str(e)}")
        return None, None

# Инициализация
data_processor, polygon_generator = init_processors()

if data_processor is None or polygon_generator is None:
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
        help="Файл должен содержать колонки: Аудитор, ТП, Дата визита, Гео/ш, Гео/д"
    )
    
    if uploaded_file is not None:
        file_key = f"{uploaded_file.name}_{uploaded_file.size}_{uploaded_file.modified}"
        
        if file_key not in st.session_state.processed_files:
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            try:
                status_text.text("📖 Чтение файла...")
                progress_bar.progress(20)
                
                # Проверка наличия колонки "Аудитор"
                df_test = pd.read_excel(uploaded_file, nrows=5, engine='openpyxl')
                if 'Аудитор' not in df_test.columns:
                    st.error("❌ В файле отсутствует колонка 'Аудитор'")
                    progress_bar.empty()
                    status_text.empty()
                    st.stop()
                
                status_text.text("🔄 Обработка данных...")
                progress_bar.progress(50)
                
                count, message = data_processor.process_uploaded_file(uploaded_file)
                
                progress_bar.progress(80)
                status_text.text("💾 Сохранение данных...")
                
                if count:
                    # Сохраняем в GitHub
                    success, save_msg = data_processor.save_data()
                    if success:
                        progress_bar.progress(100)
                        status_text.text("✅ Готово!")
                        
                        # Сохраняем в сессию
                        st.session_state.processed_files[file_key] = {
                            'count': count,
                            'message': message,
                            'save_msg': save_msg,
                            'timestamp': datetime.now().isoformat()
                        }
                        st.session_state.data_loaded = True
                        st.session_state.last_update = datetime.now()
                        
                        st.success(f"✅ {message}\n\n{save_msg}")
                    else:
                        st.error(f"❌ Ошибка сохранения: {save_msg}")
                else:
                    progress_bar.progress(100)
                    status_text.text("❌ Ошибка!")
                    st.error(message)
                
                progress_bar.empty()
                status_text.empty()
                
            except Exception as e:
                progress_bar.empty()
                status_text.empty()
                st.error(f"❌ Ошибка при загрузке: {str(e)}")
        else:
            # Показываем кэшированный результат
            file_info = st.session_state.processed_files[file_key]
            st.success(f"✅ Файл обработан: {file_info['message']}")
            st.caption(f"🕐 {file_info['timestamp']}")
    
    st.markdown("---")
    
    # Статистика с кэшированием
    st.header("📈 Статистика")
    
    @st.cache_data(ttl=60)
    def get_cached_stats():
        try:
            return data_processor.get_statistics_from_json()
        except Exception as e:
            return None
    
    stats = get_cached_stats()
    
    if stats:
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Всего визитов", stats.get('total_visits', 0))
            st.metric("Городов", stats.get('cities', 0))
        with col2:
            st.metric("Аудиторов", stats.get('total_auditors', 0))
            st.metric("Регионов", stats.get('regions', 0))
        
        if st.session_state.last_update:
            st.caption(f"🔄 Обновлено: {st.session_state.last_update.strftime('%H:%M:%S')}")
    else:
        st.info("Нет данных для статистики")
    
    st.markdown("---")
    
    # Действия с данными
    st.header("⚙️ Действия")
    
    col1, col2, col3 = st.columns([1, 1, 1])
    
    with col1:
        if st.button("🔄 Обновить", type="primary"):
            data_processor.data = data_processor.load_data()
            st.session_state.last_update = datetime.now()
            st.cache_data.clear()
            st.success("✅ Данные обновлены")
    
    with col2:
        if st.button("💾 Бэкап", type="secondary"):
            with st.spinner("Создание бэкапа..."):
                success, message = data_processor.create_backup()
                if success:
                    st.success(message)
                else:
                    st.error(message)
    
    with col3:
        if st.button("🗑️ Очистить", type="secondary"):
            if st.checkbox("Подтвердите удаление"):
                data_processor.clear_data()
                st.session_state.processed_files = {}
                st.session_state.polygons = []
                st.session_state.data_loaded = False
                st.cache_data.clear()
                st.success("✅ Данные очищены")
    
    st.markdown("---")
    
    # Параметры генерации
    st.header("🔧 Параметры полигонов")
    
    min_points = st.slider(
        "Минимальное количество точек",
        min_value=3,
        max_value=20,
        value=3,
        help="Минимальное число визитов для создания полигона"
    )
    
    buffer_km = st.slider(
        "Размер буфера (км)",
        min_value=0.0,
        max_value=5.0,
        value=0.5,
        step=0.1,
        help="Расширение полигона для учета погрешностей GPS"
    )
    
    # Фильтр по датам
    st.markdown("---")
    st.header("📅 Период анализа")
    
    col1, col2 = st.columns(2)
    with col1:
        date_from = st.date_input(
            "Дата от",
            value=datetime.now() - timedelta(days=30),
            max_value=datetime.now().date()
        )
    with col2:
        date_to = st.date_input(
            "Дата до",
            value=datetime.now().date(),
            max_value=datetime.now().date()
        )

# Основная область
tab1, tab2, tab3, tab4 = st.tabs(
    ["📋 Данные", "📐 Полигоны", "🗺️ Карта", "📥 Экспорт"]
)

with tab1:
    st.header("Просмотр данных")
    
    # Фильтры
    col1, col2, col3 = st.columns([2, 2, 1])
    
    with col1:
        auditors = data_processor.get_auditors()
        selected_auditor = st.selectbox(
            "Выберите аудитора",
            ["Все"] + auditors if auditors else ["Все"]
        )
    
    with col2:
        search = st.text_input("🔍 Поиск", placeholder="ТП, город или адрес")
    
    with col3:
        show_map = st.checkbox("Показать на карте", value=False)
    
    # Получение данных с фильтрацией по датам
    if selected_auditor == "Все":
        data_list = list(data_processor.data.values())
    else:
        data_list = data_processor.get_data_by_auditor(selected_auditor)
    
    if data_list:
        df = pd.DataFrame(data_list)
        
        # Фильтрация по датам
        if 'visit_date' in df.columns:
            df['visit_date'] = pd.to_datetime(df['visit_date'], errors='coerce')
            mask = (df['visit_date'] >= pd.to_datetime(date_from)) & (df['visit_date'] <= pd.to_datetime(date_to))
            df = df[mask]
        
        # Фильтрация по поиску
        if search and 'tp_id' in df.columns and 'city' in df.columns:
            mask = (
                df['tp_id'].str.contains(search, case=False, na=False) |
                df['city'].str.contains(search, case=False, na=False)
            )
            df = df[mask]
        
        if 'lat' in df.columns and 'lon' in df.columns:
            df['lat'] = pd.to_numeric(df['lat'], errors='coerce')
            df['lon'] = pd.to_numeric(df['lon'], errors='coerce')
            df = df.dropna(subset=['lat', 'lon'])
        
        if not df.empty:
            # Отображение карты
            if show_map:
                st.subheader("🗺️ Карта визитов")
                
                fig = px.scatter_mapbox(
                    df,
                    lat='lat',
                    lon='lon',
                    hover_name='tp_id',
                    hover_data=['auditor', 'city', 'visit_date'],
                    color='auditor',
                    zoom=10,
                    height=500,
                    title=f"Визиты аудиторов ({len(df)} точек)"
                )
                fig.update_layout(
                    mapbox_style="open-street-map",
                    margin={"r": 0, "t": 30, "l": 0, "b": 0}
                )
                st.plotly_chart(fig, use_container_width=True)
            
            # Таблица данных
            display_cols = ['tp_id', 'auditor', 'city', 'visit_date', 'lat', 'lon']
            display_cols = [col for col in display_cols if col in df.columns]
            
            st.subheader(f"📋 Данные ({len(df)} записей)")
            
            # Пагинация
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
        st.warning("⚠️ Нет данных для генерации полигонов. Сначала загрузите файл с данными.")
    else:
        col1, col2 = st.columns([3, 1])
        
        with col1:
            # Выбор аудиторов для генерации
            auditors = data_processor.get_auditors()
            selected_auditors = st.multiselect(
                "Выберите аудиторов для генерации",
                auditors,
                default=auditors[:5] if len(auditors) > 5 else auditors,
                help="Можно выбрать несколько аудиторов"
            )
        
        with col2:
            st.write("")
            st.write("")
            if st.button("🚀 Создать полигоны", type="primary", use_container_width=True):
                if not selected_auditors:
                    st.warning("Выберите хотя бы одного аудитора")
                else:
                    with st.spinner(f"Генерация полигонов для {len(selected_auditors)} аудиторов..."):
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        
                        polygons = []
                        errors = []
                        
                        for i, auditor in enumerate(selected_auditors):
                            status_text.text(f"Обработка: {auditor} ({i+1}/{len(selected_auditors)})")
                            progress_bar.progress((i + 1) / len(selected_auditors))
                            
                            # Фильтрация по датам
                            records = data_processor.get_data_by_auditor(auditor)
                            if date_from and date_to:
                                filtered_records = []
                                for record in records:
                                    if 'visit_date' in record:
                                        visit_date = pd.to_datetime(record['visit_date'])
                                        if pd.to_datetime(date_from) <= visit_date <= pd.to_datetime(date_to):
                                            filtered_records.append(record)
                                records = filtered_records
                            
                            # Временная замена данных для генератора
                            original_data = data_processor.data
                            data_processor.data = {f"{auditor}_{i}": r for i, r in enumerate(records)}
                            
                            polygon, error = polygon_generator.create_polygon_for_auditor(
                                auditor, 
                                buffer_km=buffer_km,
                                min_points=min_points
                            )
                            
                            data_processor.data = original_data
                            
                            if polygon:
                                polygons.append(polygon)
                            else:
                                errors.append(f"{auditor}: {error}")
                        
                        progress_bar.progress(1.0)
                        status_text.text("✅ Готово!")
                        
                        if polygons:
                            st.success(f"✅ Создано {len(polygons)} полигонов")
                            st.session_state.polygons = polygons
                            
                            # Показываем результаты
                            st.subheader("📊 Результаты")
                            
                            # Сводная таблица
                            summary_data = []
                            for p in polygons:
                                summary_data.append({
                                    'Аудитор': p['auditor_id'],
                                    'Точек': p['points_count'],
                                    'Площадь (км²)': f"{p.get('area_km2', 0):.2f}",
                                    'Координат': len(p['coordinates'])
                                })
                            
                            st.dataframe(
                                pd.DataFrame(summary_data),
                                use_container_width=True
                            )
                            
                            # Кнопки скачивания для каждого полигона
                            st.subheader("📥 Скачать отдельные полигоны")
                            
                            for idx, p in enumerate(polygons):
                                col1, col2, col3 = st.columns([2, 1, 1])
                                with col1:
                                    st.write(f"**{p['auditor_id']}** ({p['points_count']} точек, {p.get('area_km2', 0):.1f} км²)")
                                with col2:
                                    kml_file = polygon_generator.generate_kml([p])
                                    if kml_file and os.path.exists(kml_file):
                                        with open(kml_file, 'rb') as f:
                                            st.download_button(
                                                label="📥 KML",
                                                data=f,
                                                file_name=f"{p['auditor_id']}_{datetime.now().strftime('%Y%m%d')}.kml",
                                                mime="application/vnd.google-earth.kml+xml",
                                                key=f"download_{p['auditor_id']}_{idx}"
                                            )
                        else:
                            st.error("❌ Не удалось создать ни одного полигона")
                        
                        progress_bar.empty()
                        status_text.empty()
                        
                        if errors:
                            with st.expander(f"⚠️ Ошибки ({len(errors)})"):
                                for error in errors:
                                    st.code(error)

with tab3:
    st.header("🗺️ Визуализация полигонов")
    
    if 'polygons' in st.session_state and st.session_state.polygons:
        try:
            import folium
            from streamlit_folium import st_folium
            
            # Создаем карту
            m = folium.Map(location=[55.75, 37.61], zoom_start=10)
            
            colors = ['red', 'blue', 'green', 'purple', 'orange', 'darkred', 
                     'lightred', 'beige', 'darkblue', 'darkgreen', 'cadetblue', 
                     'darkpurple', 'white', 'pink', 'lightblue', 'lightgreen', 
                     'gray', 'black', 'lightgray']
            
            for idx, polygon_data in enumerate(st.session_state.polygons):
                color = colors[idx % len(colors)]
                
                # Добавляем полигон
                if 'coordinates' in polygon_data:
                    coords = polygon_data['coordinates']
                    # Для Folium нужны (lat, lon)
                    folium_coords = [(lat, lon) for lon, lat in coords]
                    
                    folium.Polygon(
                        locations=folium_coords,
                        color=color,
                        fill=True,
                        fill_opacity=0.2,
                        popup=f"""
                        <b>{polygon_data['auditor_id']}</b><br>
                        Точек: {polygon_data['points_count']}<br>
                        Площадь: {polygon_data.get('area_km2', 0):.1f} км²
                        """,
                        tooltip=polygon_data['auditor_id']
                    ).add_to(m)
                    
                    # Добавляем точки визитов
                    auditor_records = data_processor.get_data_by_auditor(polygon_data['auditor_id'])
                    for record in auditor_records[:50]:
                        if 'lat' in record and 'lon' in record:
                            folium.CircleMarker(
                                location=[record['lat'], record['lon']],
                                radius=3,
                                color=color,
                                fill=True,
                                popup=f"{record.get('tp_id', '')}<br>{record.get('visit_date', '')}"
                            ).add_to(m)
            
            # Добавляем легенду
            legend_html = '''
            <div style="position: fixed; bottom: 50px; left: 50px; z-index:1000; 
                        background-color: white; padding: 10px; border-radius: 5px; 
                        border: 2px solid grey; max-height: 300px; overflow-y: auto;">
                <b>Легенда</b><br>
            '''
            for idx, p in enumerate(st.session_state.polygons[:10]):
                color = colors[idx % len(colors)]
                legend_html += f'<span style="color:{color};">●</span> {p["auditor_id"]}<br>'
            legend_html += '</div>'
            
            m.get_root().html.add_child(folium.Element(legend_html))
            
            st_folium(m, width=800, height=600)
            
        except ImportError:
            st.warning("⚠️ Для отображения карты установите: pip install folium streamlit-folium")
    else:
        st.info("Сначала создайте полигоны в разделе '📐 Полигоны'")

with tab4:
    st.header("📤 Экспорт данных")
    
    if 'polygons' in st.session_state and st.session_state.polygons:
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("🗺️ Экспорт в KML")
            
            city_name = st.text_input("Название города (опционально)", key="city_name_input")
            
            if st.button("📥 Создать KML", key="create_kml_btn", use_container_width=True):
                with st.spinner("Создание KML файла..."):
                    kml_file = polygon_generator.generate_kml(
                        st.session_state.polygons,
                        city_name=city_name if city_name else None
                    )
                    
                    if kml_file and os.path.exists(kml_file):
                        st.session_state.kml_file = kml_file
                        st.success(f"✅ KML файл создан")
                    else:
                        st.error("Ошибка при создании KML файла")
            
            if 'kml_file' in st.session_state and os.path.exists(st.session_state.kml_file):
                with open(st.session_state.kml_file, 'rb') as f:
                    st.download_button(
                        label="📥 Скачать KML",
                        data=f,
                        file_name=os.path.basename(st.session_state.kml_file),
                        mime="application/vnd.google-earth.kml+xml",
                        use_container_width=True
                    )
        
        with col2:
            st.subheader("🌐 Экспорт в GeoJSON")
            
            if st.button("📥 Создать GeoJSON", use_container_width=True):
                with st.spinner("Создание GeoJSON файла..."):
                    geojson_file = polygon_generator.export_to_geojson(
                        st.session_state.polygons
                    )
                    
                    if geojson_file and os.path.exists(geojson_file):
                        with open(geojson_file, 'rb') as f:
                            st.download_button(
                                label="📥 Скачать GeoJSON",
                                data=f,
                                file_name=os.path.basename(geojson_file),
                                mime="application/json",
                                use_container_width=True
                            )
                    else:
                        st.error("Ошибка при создании GeoJSON файла")
        
        st.markdown("---")
        
        st.subheader("📊 Экспорт данных в CSV")
        
        if st.button("📥 Создать CSV", use_container_width=True):
            with st.spinner("Создание CSV файла..."):
                df_export = pd.DataFrame(list(data_processor.data.values()))
                if not df_export.empty:
                    csv = df_export.to_csv(index=False)
                    
                    st.download_button(
                        label="📥 Скачать CSV",
                        data=csv,
                        file_name=f"auditor_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
    else:
        st.info("Сначала создайте полигоны в разделе '📐 Полигоны'")

# Footer
st.markdown("---")
st.caption("🚀 Сервис разработан для генерации полигонов аудиторов на основе данных посещений")
