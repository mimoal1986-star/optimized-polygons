import pandas as pd
import streamlit as st
from shapely.geometry import Point, Polygon
from typing import Dict, Tuple, Optional

class PlanningEngine:
    """
    Класс для формирования плана визитов (АП)
    на основе Константы, Переменной и Ретро АП
    """
    
    def __init__(self):
        self.client_ratios = {}
        self.type_ratios = {}
        self.constant_df = None
        self.variable_df = None
        self.retro_df = None
        
    def load_files(self, constant_file, variable_file, retro_file):
        """Загружает три файла (без переименования колонок)"""
        
        def normalize_city_name(city):
            if pd.isna(city) or city == '':
                return ''
            city = str(city).strip()
            return city.lower().title()
        
        # Константа
        if constant_file is not None:
            self.constant_df = pd.read_excel(constant_file)
            
            if 'Latitude' in self.constant_df.columns:
                self.constant_df['Latitude'] = self.constant_df['Latitude'].astype(str).str.replace(',', '.').astype(float)
            if 'Longitude' in self.constant_df.columns:
                self.constant_df['Longitude'] = self.constant_df['Longitude'].astype(str).str.replace(',', '.').astype(float)
            
            # Нормализуем города
            if 'Город' in self.constant_df.columns:
                self.constant_df['Город'] = self.constant_df['Город'].apply(normalize_city_name)
            
            # 🔥 РАССЧИТЫВАЕМ ПРОПОРЦИИ ПО ТИПАМ ИЗ КОНСТАНТЫ
            self.type_ratios = self.calculate_type_ratios()
        
        # Переменная
        if variable_file is not None:
            self.variable_df = pd.read_excel(variable_file)
            if 'Latitude' in self.variable_df.columns:
                self.variable_df['Latitude'] = self.variable_df['Latitude'].astype(str).str.replace(',', '.').astype(float)
            if 'Longitude' in self.variable_df.columns:
                self.variable_df['Longitude'] = self.variable_df['Longitude'].astype(str).str.replace(',', '.').astype(float)
            
            # 🔥 НОРМАЛИЗУЕМ ГОРОДА
            if 'Город' in self.variable_df.columns:
                self.variable_df['Город'] = self.variable_df['Город'].apply(normalize_city_name)
        
        # Ретро
        if retro_file is not None:
            self.retro_df = pd.read_excel(retro_file)
            
            retro_mapping = {}
            for col in self.retro_df.columns:
                col_lower = col.lower().strip()
                if col_lower in ['широта', 'latitude', 'lat', 'гео/ш']:
                    retro_mapping[col] = 'Latitude'
                elif col_lower in ['долгота', 'longitude', 'lon', 'гео/д']:
                    retro_mapping[col] = 'Longitude'
                elif col_lower in ['логин', 'login', 'auditor', 'id сотрудника', 'тп']:
                    retro_mapping[col] = 'логин'
                elif col_lower in ['тип', 'type', 'red pos group']:
                    retro_mapping[col] = 'RED PoS Group'
                elif col_lower in ['адрес', 'address', 'street name']:
                    retro_mapping[col] = 'Street Name'
                elif col_lower in ['город', 'city']:
                    retro_mapping[col] = 'Город'
                elif col_lower in ['сеть', 'network', 'chain']:
                    retro_mapping[col] = 'Сеть'
            
            self.retro_df = self.retro_df.rename(columns=retro_mapping)
            
            if 'Latitude' in self.retro_df.columns:
                self.retro_df['Latitude'] = self.retro_df['Latitude'].astype(str).str.replace(',', '.').astype(float)
            if 'Longitude' in self.retro_df.columns:
                self.retro_df['Longitude'] = self.retro_df['Longitude'].astype(str).str.replace(',', '.').astype(float)
            
            # 🔥 НОРМАЛИЗУЕМ ГОРОДА
            if 'Город' in self.retro_df.columns:
                self.retro_df['Город'] = self.retro_df['Город'].apply(normalize_city_name)
        
        return self.constant_df is not None
    
    def calculate_client_ratios(self):
        if self.constant_df is None: return {}
        total_rows = len(self.constant_df)
        if total_rows == 0: return {}
        client_counts = self.constant_df['Сеть'].value_counts()
        self.client_ratios = {}
        for client, count in client_counts.items():
            self.client_ratios[client] = (count / total_rows) * 100
        return self.client_ratios
    
    def calculate_city_ratios(self):
        if self.constant_df is None: return {}
        total_rows = len(self.constant_df)
        if total_rows == 0: return {}
        city_counts = self.constant_df['Город'].value_counts()
        city_ratios = {}
        for city, count in city_counts.items():
            city_ratios[city] = (count / total_rows) * 100
        return city_ratios

    def calculate_type_ratios(self):
    """Вычисляет пропорции по типам магазинов из Константы"""
    if self.constant_df is None:
        return {}
    
    total_rows = len(self.constant_df)
    if total_rows == 0:
        return {}
    
    type_counts = self.constant_df['RED PoS Group'].value_counts()
    
    type_ratios = {}
    for type_name, count in type_counts.items():
        if type_name and type_name != 'nan':
            type_ratios[type_name] = (count / total_rows) * 100
    
    return type_ratios
    
    def get_statistics(self):
        stats = {}
        if self.constant_df is not None:
            stats['constant_count'] = len(self.constant_df)
            stats['constant_clients'] = self.constant_df['Сеть'].nunique()
            stats['constant_cities'] = self.constant_df['Город'].nunique()
        if self.variable_df is not None:
            stats['variable_count'] = len(self.variable_df)
            stats['variable_cities'] = self.variable_df['Город'].nunique()
        if self.retro_df is not None:
            stats['retro_count'] = len(self.retro_df)
            stats['retro_auditors'] = self.retro_df['логин'].nunique()
        return stats
    
    def check_point_in_polygons(self, lon, lat, polygons):
        if not polygons: return False
        point = Point(lon, lat)
        for polygon in polygons:
            if polygon.contains(point): return True
        return False
    
    def build_plan_balanced(self, fact_polygons, target_ap, 
                            constant_threshold=95, variable_threshold=95, 
                            city_tolerance_percent=0, type_tolerance_percent=0):
        """
        Формирует план визитов (АП) сбалансированно:
        - Константа → основа
        - Переменная → выравнивание полигонов (по кругу, по 1 точке)
        - Ретро → если не хватило Переменной
        - Контроль плана после каждого города
        """
        if self.constant_df is None:
            return {'status': 'error', 'message': 'Загрузите файл Константы!'}
        
        if not fact_polygons:
            return {'status': 'error', 'message': 'Сначала загрузите факт-полигоны!'}
        
        # 1. Преобразуем факт-полигоны в shapely-полигоны
        polygon_geoms = []
        polygon_auditors = []
        polygon_cities = []
        polygon_ids = []
        
        for poly_id, poly_data in fact_polygons.items():
            coords = poly_data['coordinates']
            if coords and len(coords) >= 3:
                if coords[0] != coords[-1]:
                    coords = coords + [coords[0]]
                polygon_geoms.append(Polygon(coords))
                polygon_auditors.append(poly_data['auditor_id'])
                polygon_cities.append(poly_data.get('city', 'Неизвестно'))
                polygon_ids.append(poly_id)
        
        if not polygon_geoms:
            return {'status': 'error', 'message': 'Нет валидных полигонов!'}
        
        # 2. Отбор Константы
        constant_selected = []
        constant_total = len(self.constant_df)
        error_points = []
        polygon_points = {poly_id: [] for poly_id in polygon_ids}
        polygon_count = {poly_id: 0 for poly_id in polygon_ids}
        city_count = {}
        
        for _, row in self.constant_df.iterrows():
            point = Point(row['Longitude'], row['Latitude'])
            assigned_polygon = None
            assigned_auditor = ''
            assigned_city = ''
            
            for i, poly_geom in enumerate(polygon_geoms):
                if poly_geom.contains(point):
                    assigned_polygon = polygon_ids[i]
                    assigned_auditor = polygon_auditors[i]
                    assigned_city = polygon_cities[i]
                    break
            
            if assigned_polygon:
                row_dict = row.to_dict()
                row_dict['Аудитор'] = assigned_auditor
                row_dict['полигон_id'] = assigned_polygon
                row_dict['Источник'] = 'Константа'
                constant_selected.append(row_dict)
                polygon_points[assigned_polygon].append(row_dict)
                polygon_count[assigned_polygon] += 1
                if assigned_city not in city_count:
                    city_count[assigned_city] = 0
                city_count[assigned_city] += 1
            else:
                error_points.append(row.to_dict())
        
        constant_selected_df = pd.DataFrame(constant_selected)
        final_ap = constant_selected_df.copy()
        
        if len(final_ap) >= target_ap:
            final_ap = final_ap.head(target_ap)
            return self._build_result(final_ap, constant_selected_df, pd.DataFrame(), pd.DataFrame(),
                                       error_points, target_ap, constant_total,
                                       len(self.variable_df) or 0, len(self.retro_df) or 0,
                                       constant_threshold, variable_threshold,
                                       city_tolerance_percent, type_tolerance_percent)
        
        # 3. Расчёт целевых показателей
        city_ratios = self.calculate_city_ratios()
        target_by_city = {}
        for city, ratio in city_ratios.items():
            target_by_city[city] = int(target_ap * ratio / 100)
        
        # 4. Подготовка Переменной и Ретро
        variable_points = []
        if self.variable_df is not None and not self.variable_df.empty:
            for _, row in self.variable_df.iterrows():
                point = Point(row['Longitude'], row['Latitude'])
                for i, poly_geom in enumerate(polygon_geoms):
                    if poly_geom.contains(point):
                        row_dict = row.to_dict()
                        row_dict['полигон_id'] = polygon_ids[i]
                        row_dict['Аудитор'] = polygon_auditors[i]
                        variable_points.append(row_dict)
                        break
        
        retro_points = []
        if self.retro_df is not None and not self.retro_df.empty:
            for _, row in self.retro_df.iterrows():
                point = Point(row['Longitude'], row['Latitude'])
                for i, poly_geom in enumerate(polygon_geoms):
                    if poly_geom.contains(point):
                        row_dict = row.to_dict()
                        row_dict['полигон_id'] = polygon_ids[i]
                        row_dict['Аудитор'] = polygon_auditors[i]
                        retro_points.append(row_dict)
                        break
        
        # 5. Выравнивание полигонов (по кругу)
        cities_sorted = sorted(city_count.keys(), key=lambda c: city_count.get(c, 0))
        
        for city in cities_sorted:
            city_polygons = [p for p in polygon_ids if p in polygon_points and polygon_points[p]]
            if not city_polygons:
                continue
            
            current_counts = {p: polygon_count.get(p, 0) for p in city_polygons}
            source_index = 0
            sources = [('variable', variable_points), ('retro', retro_points)]
            
            while source_index < len(sources):
                source_name, source_data = sources[source_index]
                if not source_data:
                    source_index += 1
                    continue
                
                sorted_polygons = sorted(city_polygons, key=lambda p: current_counts.get(p, 0))
                min_count = min(current_counts.values())
                max_count = max(current_counts.values())
                if max_count - min_count <= 1:
                    source_index += 1
                    continue
                
                for poly_id in sorted_polygons:
                    if len(final_ap) >= target_ap:
                        break
                    if target_by_city.get(city, 0) > 0 and city_count.get(city, 0) >= target_by_city[city]:
                        break
                    
                    for i, point_data in enumerate(source_data):
                        if point_data.get('полигон_id') == poly_id:
                            source_data.pop(i)
                            point_data['Источник'] = 'Переменная' if source_name == 'variable' else 'Ретро'
                            final_ap = pd.concat([final_ap, pd.DataFrame([point_data])], ignore_index=True)
                            current_counts[poly_id] = current_counts.get(poly_id, 0) + 1
                            city_count[city] = city_count.get(city, 0) + 1
                            break
                
                if len(final_ap) >= target_ap:
                    break
            if len(final_ap) >= target_ap:
                break
        
        # 6. Финальная статистика
        return self._build_result(final_ap, constant_selected_df, 
                                   pd.DataFrame(variable_points), 
                                   pd.DataFrame(retro_points),
                                   error_points, target_ap, constant_total,
                                   len(self.variable_df) or 0, len(self.retro_df) or 0,
                                   constant_threshold, variable_threshold,
                                   city_tolerance_percent, type_tolerance_percent,
                                   city_ratios)
    
    def _build_result(self, final_ap, constant_selected, variable_selected, retro_selected,
                      error_points, target_ap, constant_total, variable_total, retro_total,
                      constant_threshold, variable_threshold,
                      city_tolerance_percent=0, type_tolerance_percent=0,
                      city_ratios=None):
        """Формирует результат (статистика, утилизация, предупреждения)"""
        final_count = len(final_ap)
        plan_completion = (final_count / target_ap * 100) if target_ap > 0 else 0
        
        constant_fact = len(final_ap[final_ap['Источник'] == 'Константа']) if not final_ap.empty else 0
        variable_fact = len(final_ap[final_ap['Источник'] == 'Переменная']) if not final_ap.empty else 0
        retro_fact = len(final_ap[final_ap['Источник'] == 'Ретро']) if not final_ap.empty else 0
        
        constant_utilization = (constant_fact / constant_total * 100) if constant_total > 0 else 0
        variable_utilization = (variable_fact / variable_total * 100) if variable_total > 0 else 0
        retro_utilization = (retro_fact / retro_total * 100) if retro_total > 0 else 0
        
        # Проверка пропорций по городам
        city_warnings = []
        if city_ratios and not final_ap.empty:
            actual_city_counts = final_ap['Город'].value_counts()
            total = len(final_ap)
            
            # Собираем все уникальные города из final_ap И city_ratios
            all_cities = set(actual_city_counts.index) | set(city_ratios.keys())
            
            for city in all_cities:
                actual_count = actual_city_counts.get(city, 0)
                actual_ratio = (actual_count / total * 100) if total > 0 else 0
                expected_ratio = city_ratios.get(city, 0)
                
                if expected_ratio > 0:
                    deviation_percent = abs(actual_ratio - expected_ratio) / expected_ratio * 100
                else:
                    # Если города не было в Константе, но он появился в плане
                    deviation_percent = 100 if actual_count > 0 else 0
                
                if deviation_percent > city_tolerance_percent:
                    city_warnings.append(
                        f"Город {city}: ожидалось {expected_ratio:.2f}%, "
                        f"получено {actual_ratio:.2f}% (отклонение {deviation_percent:.2f}%)"
                    )
        
        # Проверка пропорций по типам
        type_warnings = []
        if not final_ap.empty:
            type_counts = final_ap['RED PoS Group'].value_counts()
            total = len(final_ap)
            for type_name, expected_ratio in self.type_ratios.items():
                actual_count = type_counts.get(type_name, 0)
                actual_ratio = (actual_count / total * 100) if total > 0 else 0
                if expected_ratio > 0:
                    deviation_percent = abs(actual_ratio - expected_ratio) / expected_ratio * 100
                else:
                    deviation_percent = 0
                if deviation_percent > type_tolerance_percent:
                    type_warnings.append(
                        f"{type_name}: ожидалось {expected_ratio:.2f}%, "
                        f"получено {actual_ratio:.2f}% (отклонение {deviation_percent:.2f}%)"
                    )
        
        # Предупреждения
        warnings = []
        if constant_utilization < constant_threshold:
            warnings.append(f'⚠️ Константа: {constant_utilization:.1f}% (< {constant_threshold}%)')
        if variable_utilization < variable_threshold:
            warnings.append(f'⚠️ Переменная: {variable_utilization:.1f}% (< {variable_threshold}%)')
        if plan_completion < 95:
            warnings.append(f'⚠️ План выполнен только на {plan_completion:.1f}% (цель {target_ap})')
        if city_warnings: warnings.extend(city_warnings)
        if type_warnings: warnings.extend(type_warnings)
        
        utilization = {
            'constant': {'total': constant_total, 'selected': constant_fact, 'utilization': constant_utilization},
            'variable': {'total': variable_total, 'selected': variable_fact, 'utilization': variable_utilization},
            'retro': {'total': retro_total, 'selected': retro_fact, 'utilization': retro_utilization}
        }
        
        status = 'success' if not warnings else 'warning'
        message = f'✅ План сформирован: {final_count} из {target_ap} ({plan_completion:.1f}%)'
        if warnings:
            message = f'⚠️ План сформирован с предупреждениями: {final_count} из {target_ap} ({plan_completion:.1f}%)'
        
        return {
            'status': status,
            'message': message,
            'warnings': warnings,
            'final_ap': final_ap,
            'constant_selected': constant_selected,
            'variable_selected': variable_selected,
            'retro_selected': retro_selected,
            'error_points': error_points,
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
