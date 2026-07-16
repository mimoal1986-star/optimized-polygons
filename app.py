import streamlit as st
import pandas as pd
from data_processor import DataProcessor
from polygon_generator import PolygonGenerator
from datetime import datetime
import json
import os
from cluster_engine import ClusterEngine
from polygon_builder import PolygonBuilder

# ==============================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ ЭКСПОРТА
# ==============================================

def generate_kml_simple(polygons):
    """Генерирует KML вручную (без simplekml)"""
    if not polygons:
        return None
    
    kml = '''<?xml version="1.0" encoding="UTF-8"?>
    <kml xmlns="http://www.opengis.net/kml/2.2">
    <Document>
    <name>Полигоны аудиторов</name>
    </Document>
    '''
    
    for poly in polygons:
        coords = poly['coordinates']
        
        # Замыкаем полигон
        if coords and coords[0] != coords[-1]:
            coords = coords + [coords[0]]
        
        coord_str = " ".join([f"{lon},{lat},0" for lon, lat in coords])
        
        kml = kml.replace('</Document>', f'''
        <Placemark>
            <name>{poly['auditor_id']} - {poly['city']} (Зона {poly['cluster_id']})</name>
            <description>
                Аудитор: {poly['auditor_id']}
                Город: {poly['city']}
                Количество точек: {poly['points_count']}
                Площадь: {poly['area_km2']:.1f} км²
            </description>
            <Style>
                <LineStyle><color>ff00ff00</color><width>2</width></LineStyle>
                <PolyStyle><color>7f00ff00</color><fill>1</fill><outline>1</outline></PolyStyle>
            </Style>
            <Polygon>
                <outerBoundaryIs>
                    <LinearRing>
                        <coordinates>{coord_str}</coordinates>
                    </LinearRing>
                </outerBoundaryIs>
            </Polygon>
        </Placemark>
        </Document>''')
    
    return kml + '\n</kml>'

def generate_csv_for_google(polygons):
    """Генерирует CSV для импорта в Google My Maps"""
    import pandas as pd
    
    rows = []
    for poly in polygons:
        center_lon, center_lat = poly['center']
        
        # Центр полигона как точка
        rows.append({
            'lat': center_lat,
            'lon': center_lon,
            'name': f"{poly['auditor_id']} - {poly['city']} (Зона {poly['cluster_id']})",
            'description': f"Площадь: {poly['area_km2']:.1f} км², Точек: {poly['points_count']}",
            'type': 'center'
        })
        
        # Границы полигона как отдельные точки
        for i, (lon, lat) in enumerate(poly['coordinates']):
            rows.append({
                'lat': lat,
                'lon': lon,
                'name': f"{poly['auditor_id']} - {poly['city']} (граница)",
                'description': f"Точка {i+1} из {len(poly['coordinates'])}",
                'type': 'boundary'
            })
    
    df = pd.DataFrame(rows)
    return df.to_csv(index=False, encoding='utf-8-sig')
    
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
    cluster_engine = ClusterEngine()
    polygon_builder = PolygonBuilder(data_processor)
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
    
    st.markdown("---")
    st.subheader("🔧 Параметры кластеризации")
    
    min_points = st.slider(
        "Минимальное количество точек в кластере",
        min_value=3,
        max_value=10,
        value=3,
        help="Кластеры с меньшим количеством точек будут отброшены"
    )
    
    auto_eps = st.checkbox(
        "Автоматический подбор eps (рекомендуется)",
        value=True,
        help="Автоматически определяет радиус кластеризации для каждого города"
    )
    
    if not auto_eps:
        eps_km = st.slider(
            "Радиус кластеризации (км)",
            min_value=0.5,
            max_value=5.0,
            value=1.0,
            step=0.1,
            help="Используется только если автоматический подбор отключен"
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
    st.header("📐 Генерация полигонов")
    
    if not data_processor.data:
        st.warning("Нет данных для генерации полигонов. Сначала загрузите файл с данными.")
    else:
        # Показываем статистику перед генерацией
        auditors = data_processor.get_auditors()
        
        if not auditors:
            st.warning("Нет аудиторов в данных")
        else:
            st.info(f"👤 Найдено аудиторов: {len(auditors)}")
            
            if st.button("🚀 Создать полигоны для всех аудиторов", type="primary"):
                with st.spinner("🔄 Кластеризация и построение полигонов..."):
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    all_polygons = []
                    errors = []
                    
                    total_auditors = len(auditors)
                    
                    for i, auditor in enumerate(auditors):
                        status_text.text(f"Обработка: {auditor} ({i+1}/{total_auditors})")
                        
                        # Создаем полигоны для аудитора
                        polygons = polygon_builder.build_polygons_for_auditor(
                            auditor,
                            buffer_km=buffer_km,
                            min_points=min_points
                        )
                        
                        if polygons:
                            all_polygons.extend(polygons)
                        else:
                            errors.append(f"{auditor}: не удалось создать полигоны")
                        
                        progress_bar.progress((i + 1) / total_auditors)
                    
                    progress_bar.progress(1.0)
                    status_text.text("✅ Готово!")
                    
                    # Сохраняем в сессию
                    st.session_state['polygons'] = all_polygons
                    
                    if all_polygons:
                        # Статистика по полигонам
                        cities_count = len(set([p['city'] for p in all_polygons]))
                        
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Всего полигонов", len(all_polygons))
                        with col2:
                            st.metric("Затронуто городов", cities_count)
                        with col3:
                            total_area = sum([p['area_km2'] for p in all_polygons])
                            st.metric("Общая площадь (км²)", f"{total_area:.1f}")
                        
                        st.success(f"✅ Создано {len(all_polygons)} полигонов для {len(auditors)} аудиторов")
                    else:
                        st.error("❌ Не удалось создать ни одного полигона")
                    
                    if errors:
                        with st.expander("⚠️ Ошибки при создании полигонов"):
                            for error in errors:
                                st.code(error)

with tab3:
    st.header("📤 Экспорт данных")
    
    if 'polygons' in st.session_state and st.session_state['polygons']:
        polygons = st.session_state['polygons']
        
        # Получаем список уникальных городов
        cities = sorted(set([p['city'] for p in polygons]))
        
        st.subheader("🏙️ Экспорт по городам")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            selected_city = st.selectbox(
                "Выберите город для экспорта:",
                ["Все города"] + cities
            )
        
        with col2:
            if st.button("📥 Создать KML", type="primary"):
                with st.spinner("Создание KML файла..."):
                    if selected_city == "Все города":
                        kml_content = generate_kml_simple(polygons)
                        filename = f"polygons_all_{datetime.now().strftime('%Y%m%d_%H%M%S')}.kml"
                        label = "Скачать все полигоны"
                    else:
                        city_polygons = [p for p in polygons if p['city'] == selected_city]
                        kml_content = generate_kml_simple(city_polygons)
                        filename = f"polygons_{selected_city}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.kml"
                        label = f"Скачать KML ({selected_city})"
                    
                    if kml_content:
                        st.download_button(
                            label=label,
                            data=kml_content.encode('utf-8'),
                            file_name=filename,
                            mime="application/vnd.google-earth.kml+xml",
                            use_container_width=True
                        )
                        st.success(f"✅ KML создан: {len(city_polygons if selected_city != 'Все города' else polygons)} полигонов")
                    else:
                        st.error("Ошибка при создании KML")
        
        # Статистика по городам
        with st.expander("📊 Статистика по городам", expanded=False):
            city_stats = {}
            for p in polygons:
                city = p['city']
                if city not in city_stats:
                    city_stats[city] = 0
                city_stats[city] += 1
            
            st.write("Количество полигонов по городам:")
            for city, count in sorted(city_stats.items()):
                st.write(f"  • {city}: {count} полигонов")
        
        st.subheader("🗺️ Экспорт всех полигонов")
        
        if st.button("📥 Создать KML (все города)"):
            with st.spinner("Создание KML файла..."):
                kml_content = generate_kml_simple(polygons)
                if kml_content:
                    st.download_button(
                        label="Скачать KML (все города)",
                        data=kml_content.encode('utf-8'),
                        file_name=f"polygons_all_{datetime.now().strftime('%Y%m%d_%H%M%S')}.kml",
                        mime="application/vnd.google-earth.kml+xml",
                        use_container_width=True
                    )
                else:
                    st.error("Ошибка при создании KML")
        
        st.subheader("📊 Экспорт в CSV для Google My Maps")
        
        if st.button("📥 Создать CSV"):
            with st.spinner("Создание CSV файла..."):
                csv_content = generate_csv_for_google(polygons)
                if csv_content:
                    st.download_button(
                        label="Скачать CSV (Google My Maps)",
                        data=csv_content.encode('utf-8-sig'),
                        file_name=f"polygons_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
                else:
                    st.error("Ошибка при создании CSV")
    else:
        st.info("Сначала создайте полигоны в разделе '📐 Полигоны'")

# Footer
st.markdown("---")
st.caption("🚀 Сервис разработан для генерации полигонов аудиторов на основе данных посещений")



