import pandas as pd
import streamlit as st
from shapely.geometry import Point, Polygon
from typing import Dict, Tuple, Optional

class PlanningEngine:
    """
    Класс для формирования плана визитов (АП)
    на основе Константы, Переменной и Ретро АП
    
    Методы:
        - load_files(): загрузка 3 Excel-файлов
        - calculate_client_ratios(): расчет пропорций клиентов из Константы
        - get_statistics(): базовая статистика по загруженным данным
    """
    
    def __init__(self):
        """Инициализация"""
        self.client_ratios = {}
        self.type_ratios = {
            'HYPERMARKET': 2.18,
            'SUPERMARKET': 6.60,
            'CONVENIENCE': 91.21
        }
        self.constant_df = None
        self.variable_df = None
        self.retro_df = None
        
    def load_files(self, constant_file, variable_file, retro_file):
        """
        Загружает три файла и нормализует названия колонок
        """
        def normalize_columns(df):
            """Приводит названия колонок к единому стандарту"""
            # Словарь: {возможное_название: стандартное_название}
            mapping = {
                'latitude': 'Latitude',
                'lat': 'Latitude',
                'широта': 'Latitude',
                'гео/ш': 'Latitude',
                'longitude': 'Longitude',
                'lon': 'Longitude',
                'долгота': 'Longitude',
                'гео/д': 'Longitude',
                'город': 'Город',
                'city': 'Город',
                'customer name': 'Customer Name',
                'клиент': 'Customer Name',
                'red pos group': 'RED PoS Group',
                'тип': 'RED PoS Group',
                'type': 'RED PoS Group',
                'логин': 'логин',
                'login': 'логин',
                'auditor': 'логин',
                'id сотрудника': 'логин',
            }
            
            # Нормализуем названия колонок
            new_columns = {}
            for col in df.columns:
                # Убираем пробелы по краям, приводим к нижнему регистру
                col_clean = col.strip().lower()
                # Ищем в маппинге
                if col_clean in mapping:
                    new_columns[col] = mapping[col_clean]
                else:
                    # Оставляем как есть, но с первой заглавной буквой
                    new_columns[col] = col.strip().title()
            
            return df.rename(columns=new_columns)
        
        # Загружаем Константу
        if constant_file is not None:
            self.constant_df = pd.read_excel(constant_file)
            self.constant_df = normalize_columns(self.constant_df)
            
            # Преобразуем координаты
            if 'Latitude' in self.constant_df.columns:
                self.constant_df['Latitude'] = self.constant_df['Latitude'].astype(str).str.replace(',', '.').astype(float)
            if 'Longitude' in self.constant_df.columns:
                self.constant_df['Longitude'] = self.constant_df['Longitude'].astype(str).str.replace(',', '.').astype(float)
        
        # Загружаем Переменную
        if variable_file is not None:
            self.variable_df = pd.read_excel(variable_file)
            self.variable_df = normalize_columns(self.variable_df)
            
            if 'Latitude' in self.variable_df.columns:
                self.variable_df['Latitude'] = self.variable_df['Latitude'].astype(str).str.replace(',', '.').astype(float)
            if 'Longitude' in self.variable_df.columns:
                self.variable_df['Longitude'] = self.variable_df['Longitude'].astype(str).str.replace(',', '.').astype(float)
        
        # Загружаем Ретро
        if retro_file is not None:
            self.retro_df = pd.read_excel(retro_file)
            
            lat_col = None
            lon_col = None
            login_col = None
            type_col = None
            address_col = None
            city_col = None
            
            for col in self.retro_df.columns:
                col_lower = col.lower().strip()
                if col_lower in ['широта', 'latitude', 'lat', 'гео/ш']:
                    lat_col = col
                elif col_lower in ['долгота', 'longitude', 'lon', 'гео/д']:
                    lon_col = col
                elif col_lower in ['логин', 'login', 'auditor', 'id сотрудника', 'тп']:
                    login_col = col
                elif col_lower in ['тип', 'type', 'red pos group']:
                    type_col = col
                elif col_lower in ['адрес', 'address', 'street name']:
                    address_col = col
                elif col_lower in ['город', 'city']:
                    city_col = col
            
            if lat_col:
                self.retro_df = self.retro_df.rename(columns={lat_col: 'Latitude'})
            if lon_col:
                self.retro_df = self.retro_df.rename(columns={lon_col: 'Longitude'})
            if login_col:
                self.retro_df = self.retro_df.rename(columns={login_col: 'логин'})
            if type_col:
                self.retro_df = self.retro_df.rename(columns={type_col: 'RED PoS Group'})
            if address_col:
                self.retro_df = self.retro_df.rename(columns={address_col: 'Street Name'})
            if city_col:
                self.retro_df = self.retro_df.rename(columns={city_col: 'Город'})
            
            # Преобразуем координаты
            self.retro_df['Latitude'] = self.retro_df['Latitude'].astype(str).str.replace(',', '.').astype(float)
            self.retro_df['Longitude'] = self.retro_df['Longitude'].astype(str).str.replace(',', '.').astype(float)
        
        return self.constant_df is not None
    
    def calculate_client_ratios(self):
        """
        Вычисляет пропорции по клиентам из Константы
        
        Returns:
            dict: {client_name: ratio_in_percent}
            
        Пример:
            {'ООО ХОЛЛИФУД': 45.2, 'ООО МАГНИТ': 30.1, ...}
        """
        if self.constant_df is None:
            return {}
        
        total_rows = len(self.constant_df)
        if total_rows == 0:
            return {}
        
        client_counts = self.constant_df['Customer Name'].value_counts()
        
        self.client_ratios = {}
        for client, count in client_counts.items():
            self.client_ratios[client] = (count / total_rows) * 100
        
        return self.client_ratios
    
    def get_statistics(self):
        """
        Возвращает базовую статистику по загруженным данным
        
        Returns:
            dict: статистика по каждому источнику
            
        Пример:
            {
                'constant_count': 3500,
                'constant_clients': 45,
                'constant_cities': 16,
                'variable_count': 2000,
                'variable_cities': 15,
                'retro_count': 500,
                'retro_auditors': 30
            }
        """
        stats = {}
        
        if self.constant_df is not None:
            stats['constant_count'] = len(self.constant_df)
            stats['constant_clients'] = self.constant_df['Customer Name'].nunique()
            stats['constant_cities'] = self.constant_df['Город'].nunique()
        
        if self.variable_df is not None:
            stats['variable_count'] = len(self.variable_df)
            stats['variable_cities'] = self.variable_df['Город'].nunique()
        
        if self.retro_df is not None:
            stats['retro_count'] = len(self.retro_df)
            stats['retro_auditors'] = self.retro_df['логин'].nunique()
        
        return stats

    
    def check_point_in_polygons(self, lon, lat, polygons):
        """
        Проверяет, попадает ли точка хотя бы в один полигон
        
        Args:
            lon: долгота точки
            lat: широта точки
            polygons: список полигонов (shapely.geometry.Polygon)
        
        Returns:
            bool: True если точка попала хотя бы в один полигон
        """
        if not polygons:
            return False
        
        point = Point(lon, lat)
        
        for polygon in polygons:
            if polygon.contains(point):
                return True
        
        return False
        
    def build_plan(self, retro_polygons, target_ap, constant_threshold=95, variable_threshold=95, type_tolerance=0):
        """
        Формирует план визитов (АП) по трёхэтапной логике:
        1. Константа → основа
        2. Переменная → добираем до 100% (без дубликатов)
        3. Ретро → добираем до 100% (без дубликатов)
        Статистика считается только по факту попадания в final_ap
        """
        if self.constant_df is None:
            return {'status': 'error', 'message': 'Загрузите файл Константы!'}
        
        if not retro_polygons:
            return {'status': 'error', 'message': 'Сначала создайте ретро-полигоны!'}

        # ==============================================
        # ПРЕОБРАЗУЕМ retro_polygons В SHAPELY-ПОЛИГОНЫ
        # ==============================================
        polygon_geoms = []
        for poly_data in retro_polygons:
            coords = poly_data['coordinates']
            if coords and len(coords) >= 3:
                if coords[0] != coords[-1]:
                    coords = coords + [coords[0]]
                polygon_geoms.append(Polygon(coords))
        
        if not polygon_geoms:
            return {'status': 'error', 'message': 'Нет валидных полигонов!'}
            
        # ==============================================
        # ШАГ 1: Отбор Константы → формируем основу АП
        # ==============================================
        constant_selected = []
        constant_total = len(self.constant_df)
        
        for _, row in self.constant_df.iterrows():
            point = Point(row['Longitude'], row['Latitude'])
            assigned_auditor = ''
            
            for i, poly_geom in enumerate(polygon_geoms):
                if poly_geom.contains(point):
                    assigned_auditor = retro_polygons[i]['auditor_id']
                    break
            
            if assigned_auditor:
                row['Аудитор'] = assigned_auditor
                constant_selected.append(row)
        
        constant_selected_df = pd.DataFrame(constant_selected)
        
        # Формируем финальную АП из Константы
        final_ap = constant_selected_df.copy()
        final_ap['Источник'] = 'Константа'
        
        # Проверяем, достигнут ли target_ap
        if len(final_ap) >= target_ap:
            # Статистика считается в конце
            pass  # переходим к статистике
        
        # ==============================================
        # ШАГ 2: Отбор Переменной → добираем до target_ap
        # ==============================================
        variable_total = len(self.variable_df) if self.variable_df is not None else 0
        
        if self.variable_df is not None and variable_total > 0:
            # Отбираем все точки Переменной, попавшие в полигоны
            variable_all = []
            for _, row in self.variable_df.iterrows():
                point = Point(row['Longitude'], row['Latitude'])
                assigned_auditor = ''
                
                for i, poly_geom in enumerate(polygon_geoms):
                    if poly_geom.contains(point):
                        assigned_auditor = retro_polygons[i]['auditor_id']
                        break
                
                if assigned_auditor:
                    row['Аудитор'] = assigned_auditor
                    variable_all.append(row)
            
            variable_all_df = pd.DataFrame(variable_all)
            
            # Удаляем дубликаты с текущей final_ap (по координатам)
            if not variable_all_df.empty and not final_ap.empty:
                # Создаём множество координат из final_ap
                existing_coords = set(zip(final_ap['Longitude'], final_ap['Latitude']))
                # Оставляем только те точки, которых нет в final_ap
                variable_all_df = variable_all_df[
                    ~variable_all_df.apply(
                        lambda row: (row['Longitude'], row['Latitude']) in existing_coords,
                        axis=1
                    )
                ]
            
            # Берём только сколько не хватает до target_ap
            current_count = len(final_ap)
            needed = max(0, target_ap - current_count)
            
            if needed > 0 and not variable_all_df.empty:
                variable_to_add = variable_all_df.head(needed).copy()
                variable_to_add['Источник'] = 'Переменная'
                final_ap = pd.concat([final_ap, variable_to_add], ignore_index=True)
        
        # ==============================================
        # ШАГ 3: Отбор Ретро → добираем до target_ap
        # ==============================================
        retro_total = len(self.retro_df) if self.retro_df is not None else 0
        
        if self.retro_df is not None and retro_total > 0:
            # Отбираем все точки Ретро, попавшие в полигоны
            retro_all = []
            for _, row in self.retro_df.iterrows():
                point = Point(row['Longitude'], row['Latitude'])
                assigned_auditor = ''
                
                for i, poly_geom in enumerate(polygon_geoms):
                    if poly_geom.contains(point):
                        assigned_auditor = retro_polygons[i]['auditor_id']
                        break
                
                if assigned_auditor:
                    row['Аудитор'] = assigned_auditor
                    retro_all.append(row)
            
            retro_all_df = pd.DataFrame(retro_all)
            
            # Удаляем дубликаты с текущей final_ap (по координатам)
            if not retro_all_df.empty and not final_ap.empty:
                existing_coords = set(zip(final_ap['Longitude'], final_ap['Latitude']))
                retro_all_df = retro_all_df[
                    ~retro_all_df.apply(
                        lambda row: (row['Longitude'], row['Latitude']) in existing_coords,
                        axis=1
                    )
                ]
            
            # Берём только сколько не хватает до target_ap
            current_count = len(final_ap)
            needed = max(0, target_ap - current_count)
            
            if needed > 0 and not retro_all_df.empty:
                retro_to_add = retro_all_df.head(needed).copy()
                retro_to_add['Источник'] = 'Ретро'
                final_ap = pd.concat([final_ap, retro_to_add], ignore_index=True)
        
        # ==============================================
        # ШАГ 4: Финальная статистика (только по факту)
        # ==============================================
        final_count = len(final_ap)
        plan_completion = (final_count / target_ap * 100) if target_ap > 0 else 0
        
        # Утилизация считается ТОЛЬКО по факту попадания в final_ap
        # Считаем, сколько точек из каждого источника реально попало в final_ap
        constant_fact = len(final_ap[final_ap['Источник'] == 'Константа'])
        variable_fact = len(final_ap[final_ap['Источник'] == 'Переменная'])
        retro_fact = len(final_ap[final_ap['Источник'] == 'Ретро'])
        
        constant_utilization = (constant_fact / constant_total * 100) if constant_total > 0 else 0
        variable_utilization = (variable_fact / variable_total * 100) if variable_total > 0 else 0
        retro_utilization = (retro_fact / retro_total * 100) if retro_total > 0 else 0
        
        # ==============================================
        # ШАГ 5: Проверка пропорций по типам (мягкая)
        # ==============================================
        type_warnings = []
        if len(final_ap) > 0:
            type_counts = final_ap['RED PoS Group'].value_counts()
            total = len(final_ap)
            
            for type_name, expected_ratio in self.type_ratios.items():
                actual_count = type_counts.get(type_name, 0)
                actual_ratio = (actual_count / total * 100) if total > 0 else 0
                deviation = abs(actual_ratio - expected_ratio)
                
                if deviation > type_tolerance:
                    type_warnings.append(
                        f"{type_name}: ожидалось {expected_ratio:.2f}%, "
                        f"получено {actual_ratio:.2f}% (отклонение {deviation:.2f}%)"
                    )
        
        # ==============================================
        # ШАГ 6: Мягкие проверки (предупреждения)
        # ==============================================
        warnings = []
        
        if constant_utilization < constant_threshold:
            warnings.append(f'⚠️ Константа: {constant_utilization:.1f}% (< {constant_threshold}%)')
        
        if variable_utilization < variable_threshold:
            warnings.append(f'⚠️ Переменная: {variable_utilization:.1f}% (< {variable_threshold}%)')
        
        if plan_completion < 95:
            warnings.append(f'⚠️ План выполнен только на {plan_completion:.1f}% (цель {target_ap})')
        
        warnings.extend(type_warnings)
        
        # ==============================================
        # ШАГ 7: Утилизация (для отчёта)
        # ==============================================
        utilization = {
            'constant': {
                'total': constant_total,
                'selected': constant_fact,
                'utilization': constant_utilization
            },
            'variable': {
                'total': variable_total,
                'selected': variable_fact,
                'utilization': variable_utilization
            },
            'retro': {
                'total': retro_total,
                'selected': retro_fact,
                'utilization': retro_utilization
            }
        }
        
        # ==============================================
        # ШАГ 8: Результат
        # ==============================================
        status = 'success' if not warnings else 'warning'
        message = f'✅ План сформирован: {final_count} из {target_ap} ({plan_completion:.1f}%)'
        if warnings:
            message = f'⚠️ План сформирован с предупреждениями: {final_count} из {target_ap} ({plan_completion:.1f}%)'
        
        return {
            'status': status,
            'message': message,
            'warnings': warnings,
            'final_ap': final_ap,
            'constant_selected': constant_selected_df,
            'variable_selected': variable_all_df if 'variable_all_df' in locals() else pd.DataFrame(),
            'retro_selected': retro_all_df if 'retro_all_df' in locals() else pd.DataFrame(),
            'statistics': {
                'target_ap': target_ap,
                'final_count': final_count,
                'plan_completion': plan_completion,
                'constant_total': constant_total,
                'constant_selected': constant_fact,
                'constant_utilization': constant_utilization,
                'variable_total': variable_total,
                'variable_selected': variable_fact,
                'variable_utilization': variable_utilization,
                'retro_total': retro_total,
                'retro_selected': retro_fact,
                'retro_utilization': retro_utilization
            },
            'utilization': utilization
        }


    def _select_retro_points(self, retro_polygons, needed_count, active_clients):
        """
        Отбирает точки из Ретро, если не хватает для достижения целевого объема
        
        Args:
            retro_polygons: список полигонов
            needed_count: сколько точек нужно добавить
            active_clients: список активных клиентов (из Константы)
        
        Returns:
            DataFrame: отобранные точки из Ретро
        """
        if self.retro_df is None or len(self.retro_df) == 0:
            return pd.DataFrame()
        
        selected = []
        
        for _, row in self.retro_df.iterrows():
            # if row['логин'] not in active_clients:
            #     continue
            
            if self.check_point_in_polygons(row['долгота'], row['широта'], retro_polygons):
                selected.append(row)
            
            if len(selected) >= needed_count:
                break
        
        return pd.DataFrame(selected)
