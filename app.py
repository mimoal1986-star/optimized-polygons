import streamlit as st
import pandas as pd
from data_processor import DataProcessor
from datetime import datetime
import json
import os
from cluster_engine import ClusterEngine
from polygon_builder import PolygonBuilder
from planning_engine import PlanningEngine

# ==============================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ ЭКСПОРТА
# ==============================================

def generate_kml_simple(polygons):
    """Генерирует KML с уникальными цветами для каждого аудитора в городе"""
    if not polygons:
        return None
    
    # ==============================================
    # 1. Генерация цветов для каждого аудитора в каждом городе
    # ==============================================
    import hashlib
    
    def get_color_for_auditor(city, auditor_id):
        """Генерирует уникальный цвет для аудитора в конкретном городе"""
        # Создаем уникальный ключ: город + аудитор
        key = f"{city}_{auditor_id}"
        
        # Хешируем для получения стабильного цвета
        hash_obj = hashlib.md5(key.encode())
        hash_hex = hash_obj.hexdigest()
        
        # Берем первые 6 символов для цвета
        color = hash_hex[:6]
        
        return color
    
    # ==============================================
    # 2. Группируем полигоны по городу и аудитору
    # ==============================================
    city_auditor_colors = {}
    for poly in polygons:
        city = poly['city']
        auditor = poly['auditor_id']
        key = f"{city}_{auditor}"
        if key not in city_auditor_colors:
            city_auditor_colors[key] = get_color_for_auditor(city, auditor)
    
    # ==============================================
    # 3. Генерируем KML
    # ==============================================
    kml = '''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document>
<name>Полигоны аудиторов</name>
</Document>
'''
    
    for poly in polygons:
        coords = poly['coordinates']
        city = poly['city']
        auditor = poly['auditor_id']
        
        # Замыкаем полигон
        if coords and coords[0] != coords[-1]:
            coords = coords + [coords[0]]
        
        coord_str = "\n".join([f"{lon},{lat},0" for lon, lat in coords])
        
        # Получаем цвет для этого аудитора в этом городе
        key = f"{city}_{auditor}"
        color = city_auditor_colors.get(key, "ff00ff00")  # зеленый по умолчанию
        
        # Для KML цвет в формате AABBGGRR (прозрачность, синий, зеленый, красный)
        # Нам нужен цвет в формате ffRRGGBB
        r = int(color[0:2], 16)
        g = int(color[2:4], 16)
        b = int(color[4:6], 16)
        
        # Формат KML: AABBGGRR, но мы хотим ffRRGGBB (непрозрачный, RGB)
        kml_color = f"ff{r:02x}{g:02x}{b:02x}"
        kml_fill_color = f"7f{r:02x}{g:02x}{b:02x}"  # полупрозрачный для заливки
        
        kml = kml.replace('</Document>', f'''
<Placemark>
    <name>{auditor} - {city} (Зона {poly['cluster_id']})</name>
    <description>
        Аудитор: {auditor}
        Город: {city}
        Количество точек: {poly['points_count']}
        Площадь: {poly['area_km2']:.1f} км²
    </description>
    <Style>
        <LineStyle><color>{kml_color}</color><width>2</width></LineStyle>
        <PolyStyle><color>{kml_fill_color}</color><fill>1</fill><outline>1</outline></PolyStyle>
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
    return dp

try:
    data_processor = init_processors()
    cluster_engine = ClusterEngine()
    polygon_builder = PolygonBuilder(data_processor)
    planning_engine = PlanningEngine()
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
        help="Файл должен содержать колонки: ТП, Гео/ш, Гео/д"
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
            
            # Показываем ошибки, если они есть
            if 'error_points' in st.session_state:
                if st.session_state['error_points']:
                    with st.expander("⚠️ Найдены ошибочные координаты"):
                        st.warning(f"Обнаружено {len(st.session_state['error_points'])} точек с некорректными координатами (дальше 50 км от центра города)")
                        
                        excel_data = data_processor.export_errors_to_excel(st.session_state['error_points'])
                        if excel_data:
                            st.download_button(
                                label="📥 Скачать ошибочные точки (Excel)",
                                data=excel_data,
                                file_name=f"ошибочные_точки_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            )
                else:
                    st.success("✅ Ошибок не найдено! Все координаты корректны.")                     
    
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
tab1, tab2, tab3, tab4 = st.tabs(
    ["📋 Данные", "📐 Полигоны", "📥 Экспорт", "📅 Планирование"]
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
                        
                        col1, col2, col3, col4 = st.columns(4)
                        
                        with col1:
                            st.metric("Целевой объем", stats.get('target_ap', 0))
                            st.metric("Фактический объем", stats.get('final_count', 0))
                            st.metric("Выполнение плана", f"{stats.get('plan_completion', 0):.1f}%")
                        
                        with col2:
                            st.metric("Константа (всего)", stats.get('constant_total', 0))
                            st.metric("Константа (отобрано)", stats.get('constant_selected', 0))
                            st.metric("Утилизация константы", f"{stats.get('constant_utilization', 0):.1f}%")
                        
                        with col3:
                            st.metric("Переменная (всего)", stats.get('variable_total', 0))
                            st.metric("Переменная (отобрано)", stats.get('variable_selected', 0))
                            st.metric("Утилизация переменной", f"{stats.get('variable_utilization', 0):.1f}%")
                        
                        with col4:
                            st.metric("Ретро (всего)", stats.get('retro_total', 0))
                            st.metric("Ретро (отобрано)", stats.get('retro_selected', 0))
                            st.metric("Утилизация ретро", f"{stats.get('retro_utilization', 0):.1f}%")
                        
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

with tab4:
    st.header("📅 Формирование плана визитов (АП)")
    st.markdown("---")
    
    # ==============================================
    # 1. ЗАГРУЗКА ФАЙЛОВ
    # ==============================================
    st.subheader("📤 Загрузка файлов АП")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        constant_file = st.file_uploader(
            "Константа АП",
            type=['xlsx'],
            help="Файл с постоянными точками (≈70% плана)",
            key="constant_uploader"
        )
    
    with col2:
        variable_file = st.file_uploader(
            "Переменная АП",
            type=['xlsx'],
            help="Файл с переменными точками (≈30% плана)",
            key="variable_uploader"
        )
    
    with col3:
        retro_file = st.file_uploader(
            "Ретро АП",
            type=['xlsx'],
            help="Файл с точками из прошлых периодов (max 10%)",
            key="retro_uploader"
        )
    
    # ==============================================
    # 2. ЗАГРУЗКА И СТАТИСТИКА
    # ==============================================
    if constant_file is not None:
        with st.spinner("Загрузка данных..."):
            # Загружаем файлы
            planning_engine.load_files(constant_file, variable_file, retro_file)
            
            # Вычисляем пропорции клиентов
            if constant_file is not None:
                client_ratios = planning_engine.calculate_client_ratios()
                st.session_state['client_ratios'] = client_ratios
            
            # Показываем статистику
            stats = planning_engine.get_statistics()
            
            st.success("✅ Данные загружены")
            
            st.subheader("📊 Статистика по загруженным данным")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("Константа (строк)", stats.get('constant_count', 0))
                st.caption(f"Клиентов: {stats.get('constant_clients', 0)}")
                st.caption(f"Городов: {stats.get('constant_cities', 0)}")
            
            with col2:
                st.metric("Переменная (строк)", stats.get('variable_count', 0))
                st.caption(f"Городов: {stats.get('variable_cities', 0)}")
            
            with col3:
                st.metric("Ретро (строк)", stats.get('retro_count', 0))
                st.caption(f"Аудиторов: {stats.get('retro_auditors', 0)}")
            
            # Показываем пропорции клиентов
            if 'client_ratios' in st.session_state and st.session_state['client_ratios']:
                with st.expander("📊 Пропорции по клиентам (из Константы)"):
                    client_ratios = st.session_state['client_ratios']
                    # Сортируем по убыванию
                    sorted_clients = sorted(client_ratios.items(), key=lambda x: x[1], reverse=True)
                    
                    # Показываем топ-10
                    st.write("**Топ-10 клиентов:**")
                    for i, (client, ratio) in enumerate(sorted_clients[:10], 1):
                        st.write(f"{i}. **{client}** — {ratio:.1f}%")
                    
                    if len(sorted_clients) > 10:
                        st.caption(f"... и еще {len(sorted_clients) - 10} клиентов")
                    
                    # Кнопка для скачивания полного списка
                    if st.button("📥 Скачать полный список клиентов (CSV)"):
                        import pandas as pd
                        df_clients = pd.DataFrame(sorted_clients, columns=['Клиент', 'Доля (%)'])
                        csv = df_clients.to_csv(index=False, encoding='utf-8-sig')
                        st.download_button(
                            label="Скачать CSV",
                            data=csv,
                            file_name="пропорции_клиентов.csv",
                            mime="text/csv"
                        )
    
    # ==============================================
    # 3. ПАРАМЕТРЫ ФОРМИРОВАНИЯ ПЛАНА
    # ==============================================
    st.markdown("---")
    st.subheader("⚙️ Параметры формирования плана")
    
    col1, col2 = st.columns(2)
    
    with col1:
        target_ap = st.number_input(
            "Целевой объем АП (месяц)",
            min_value=1,
            max_value=100000,
            value=5000,
            step=100,
            help="Общее количество визитов, которое нужно запланировать"
        )
        
        constant_threshold = st.slider(
            "Порог константы (%)",
            min_value=0,
            max_value=100,
            value=95,
            help="Минимальный % константы, который должен попасть в АП"
        )
    
    with col2:
        variable_threshold = st.slider(
            "Порог переменной (%)",
            min_value=0,
            max_value=100,
            value=95,
            help="Минимальный % от целевого АП, который должен быть собран"
        )
        
        type_tolerance = st.slider(
            "Допуск по типам магазинов (пп)",
            min_value=0,
            max_value=100,
            value=0,
            help="Отклонение от пропорций в процентных пунктах (п.п.). 100% = можно сделать 100% любого типа"
        )
    
    # ==============================================
    # 4. КНОПКА ЗАПУСКА
    # ==============================================
    st.markdown("---")
    
    if st.button("🚀 Сформировать план", type="primary"):
        if constant_file is None:
            st.error("❌ Загрузите файл Константы!")
        else:
            # Проверяем наличие ретро-полигонов
            if 'polygons' not in st.session_state or not st.session_state['polygons']:
                st.error("❌ Сначала создайте ретро-полигоны в разделе '📐 Полигоны'!")
            else:
                with st.spinner("🔄 Формирование плана визитов..."):
                    retro_polygons = st.session_state['polygons']
                    
                    # Извлекаем полигоны из данных
                    polygon_geoms = []
                    for poly_data in retro_polygons:
                        coords = poly_data['coordinates']
                        if coords and len(coords) >= 3:
                            from shapely.geometry import Polygon
                            # Замыкаем полигон если нужно
                            if coords[0] != coords[-1]:
                                coords = coords + [coords[0]]
                            polygon_geoms.append(Polygon(coords))
                    
                    if not polygon_geoms:
                        st.error("❌ Нет валидных полигонов для проверки!")
                    else:
                        # Запускаем формирование плана
                        result = planning_engine.build_plan(
                            retro_polygons=polygon_geoms,
                            target_ap=target_ap,
                            constant_threshold=constant_threshold,
                            variable_threshold=variable_threshold,
                            type_tolerance=type_tolerance
                        )
                        
                        # Сохраняем результат в session_state
                        st.session_state['plan_result'] = result
                        
                        # ==============================================
                        # ОТОБРАЖЕНИЕ РЕЗУЛЬТАТА
                        # ==============================================
                        
                        # 1. Статус
                        if result['status'] == 'success':
                            st.success(result['message'])
                        elif result['status'] == 'warning':
                            st.warning(result['message'])
                            if 'warnings' in result and result['warnings']:
                                with st.expander("⚠️ Детали предупреждений"):
                                    for warning in result['warnings']:
                                        st.write(f"- {warning}")
                        else:
                            st.error(result['message'])
                            st.stop()
                        
                        # 2. Статистика
                        stats = result.get('statistics', {})
                        util = result.get('utilization', {})
                        
                        st.subheader("📊 Статистика формирования плана")
                        
                        col1, col2, col3 = st.columns(3)
                        
                        with col1:
                            st.metric("Целевой объем", stats.get('target_ap', 0))
                            st.metric("Фактический объем", stats.get('final_count', 0))
                            st.metric("Выполнение плана", f"{stats.get('plan_completion', 0):.1f}%")
                        
                        with col2:
                            st.metric("Константа (всего)", stats.get('constant_total', 0))
                            st.metric("Константа (отобрано)", stats.get('constant_selected', 0))
                            st.metric("Утилизация константы", f"{stats.get('constant_utilization', 0):.1f}%")
                        
                        with col3:
                            st.metric("Переменная (всего)", stats.get('variable_total', 0))
                            st.metric("Переменная (отобрано)", stats.get('variable_selected', 0))
                            st.metric("Утилизация переменной", f"{stats.get('variable_utilization', 0):.1f}%")
                        
                        # 3. Детальная утилизация
                        with st.expander("📊 Детальная утилизация источников"):
                            st.write("**Источники АП:**")
                            st.write(f"- Константа: {util['constant']['selected']} из {util['constant']['total']} ({util['constant']['utilization']:.1f}%)")
                            st.write(f"- Переменная: {util['variable']['selected']} из {util['variable']['total']} ({util['variable']['utilization']:.1f}%)")
                            st.write(f"- Ретро: {util['retro']['selected']} из {util['retro']['total']} ({util['retro']['utilization']:.1f}%)")
                        
                        # 4. Пропорции по типам (сравнение)
                        if 'final_ap' in result and not result['final_ap'].empty:
                            with st.expander("📊 Пропорции по типам магазинов"):
                                final_ap = result['final_ap']
                                type_counts = final_ap['RED PoS Group'].value_counts()
                                total = len(final_ap)
                                
                                type_data = []
                                for type_name, expected_ratio in planning_engine.type_ratios.items():
                                    actual_count = type_counts.get(type_name, 0)
                                    actual_ratio = (actual_count / total * 100) if total > 0 else 0
                                    type_data.append({
                                        'Тип': type_name,
                                        'Ожидаемая доля (%)': expected_ratio,
                                        'Фактическая доля (%)': actual_ratio,
                                        'Отклонение': actual_ratio - expected_ratio
                                    })
                                
                                st.dataframe(pd.DataFrame(type_data), use_container_width=True, hide_index=True)
                        
                        # 5. Кнопка экспорта финальной АП
                        if 'final_ap' in result and not result['final_ap'].empty:
                            st.markdown("---")
                            st.subheader("📥 Экспорт финальной АП")
                            
                            # Преобразуем в нужный формат
                            export_df = result['final_ap'].copy()
                            
                            # Добавляем колонку "Источник" если её нет
                            if 'Источник' not in export_df.columns:
                                # Определяем источник по наличию в соответствующих DataFrame
                                constant_ids = set(result['constant_selected'].index) if not result['constant_selected'].empty else set()
                                variable_ids = set(result['variable_selected'].index) if not result['variable_selected'].empty else set()
                                
                                def get_source(idx):
                                    if idx in constant_ids:
                                        return 'Константа'
                                    elif idx in variable_ids:
                                        return 'Переменная'
                                    else:
                                        return 'Ретро'
                                
                                export_df['Источник'] = export_df.index.map(get_source)
                            
                            # Выбираем нужные колонки
                            columns_order = ['Customer Name', 'RED PoS Group', 'Город', 'Street Name', 'Longitude', 'Latitude', 'Источник']
                            available_cols = [col for col in columns_order if col in export_df.columns]
                            export_df = export_df[available_cols]
                            
                            # Переименовываем для понятности
                            rename_map = {
                                'Customer Name': 'Имя клиента',
                                'RED PoS Group': 'Тип магазина',
                                'Город': 'Город',
                                'Street Name': 'Адрес',
                                'Longitude': 'Долгота',
                                'Latitude': 'Широта'
                            }
                            export_df = export_df.rename(columns=rename_map)
                            
                            st.dataframe(export_df.head(20), use_container_width=True)
                            st.caption(f"Показано первые 20 из {len(export_df)} строк")
                            
                            # Кнопка скачивания
                            import io
                            output = io.BytesIO()
                            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                                export_df.to_excel(writer, sheet_name='Финальная АП', index=False)
                                
                                # Добавляем лист со статистикой
                                stats_df = pd.DataFrame([
                                    ['Параметр', 'Значение'],
                                    ['Целевой объем', stats.get('target_ap', 0)],
                                    ['Фактический объем', stats.get('final_count', 0)],
                                    ['Выполнение плана', f"{stats.get('plan_completion', 0):.1f}%"],
                                    ['Константа (отобрано)', stats.get('constant_selected', 0)],
                                    ['Переменная (отобрано)', stats.get('variable_selected', 0)],
                                    ['Ретро (отобрано)', stats.get('retro_selected', 0)],
                                ])
                                stats_df.to_excel(writer, sheet_name='Статистика', index=False, header=False)
                            
                            output.seek(0)
                            
                            st.download_button(
                                label="📥 Скачать финальную АП (Excel)",
                                data=output.getvalue(),
                                file_name=f"финальная_АП_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                use_container_width=True
                            )
# Footer
st.markdown("---")
st.caption("🚀 Сервис разработан для генерации полигонов аудиторов на основе данных посещений")



