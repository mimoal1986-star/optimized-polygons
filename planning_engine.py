import pandas as pd
import streamlit as st
from shapely.geometry import Point
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
            self.retro_df = normalize_columns(self.retro_df)
            
            if 'широта' in self.retro_df.columns:
                self.retro_df['широта'] = self.retro_df['широта'].astype(str).str.replace(',', '.').astype(float)
            if 'долгота' in self.retro_df.columns:
                self.retro_df['долгота'] = self.retro_df['долгота'].astype(str).str.replace(',', '.').astype(float)
        
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
        Формирует план визитов (АП) на основе трех источников
        
        Args:
            retro_polygons: список полигонов из st.session_state['polygons']
            target_ap: целевой объем АП (месяц)
            constant_threshold: минимальный % константы в АП (по умолчанию 95%)
            variable_threshold: минимальный % от целевого АП для переменной (по умолчанию 95%)
            type_tolerance: допуск по типам магазинов в % (по умолчанию 0)
        
        Returns:
            dict: {
                'status': 'success' | 'warning' | 'error',
                'message': str,
                'final_ap': DataFrame,
                'statistics': dict,
                'utilization': dict
            }
        """
        if self.constant_df is None:
            return {'status': 'error', 'message': 'Загрузите файл Константы!'}
        
        if not retro_polygons:
            return {'status': 'error', 'message': 'Сначала создайте ретро-полигоны!'}
        
        # ==============================================
        # ШАГ 1: Отбор Константы
        # ==============================================
        constant_selected = []
        constant_total = len(self.constant_df)
        
        for _, row in self.constant_df.iterrows():
            if self.check_point_in_polygons(row['Longitude'], row['Latitude'], retro_polygons):
                constant_selected.append(row)
        
        constant_selected_df = pd.DataFrame(constant_selected)
        constant_utilization = (len(constant_selected_df) / constant_total * 100) if constant_total > 0 else 0
        
        # Проверка порога константы
        if constant_utilization < constant_threshold:
            return {
                'status': 'warning',
                'message': f'⚠️ Константа: {constant_utilization:.1f}% (< {constant_threshold}%)',
                'constant_selected': constant_selected_df,
                'constant_utilization': constant_utilization,
                'statistics': {
                    'constant_total': constant_total,
                    'constant_selected': len(constant_selected_df),
                    'constant_utilization': constant_utilization
                }
            }
        
        # ==============================================
        # ШАГ 2: Отбор Переменной
        # ==============================================
        variable_selected = []
        variable_total = len(self.variable_df) if self.variable_df is not None else 0
        
        if self.variable_df is not None and variable_total > 0:
            for _, row in self.variable_df.iterrows():
                if self.check_point_in_polygons(row['Longitude'], row['Latitude'], retro_polygons):
                    variable_selected.append(row)
            
            variable_selected_df = pd.DataFrame(variable_selected)
            variable_utilization = (len(variable_selected_df) / variable_total * 100) if variable_total > 0 else 0
        else:
            variable_selected_df = pd.DataFrame()
            variable_utilization = 0
        
        # ==============================================
        # ШАГ 3: Проверка пропорций по типам
        # ==============================================
        temp_ap = pd.concat([constant_selected_df, variable_selected_df], ignore_index=True)
        
        if len(temp_ap) > 0:
            type_counts = temp_ap['RED PoS Group'].value_counts()
            total = len(temp_ap)
            
            type_errors = []
            for type_name, expected_ratio in self.type_ratios.items():
                actual_count = type_counts.get(type_name, 0)
                actual_ratio = (actual_count / total * 100) if total > 0 else 0
                deviation = abs(actual_ratio - expected_ratio)
                
                if deviation > type_tolerance:
                    type_errors.append(
                        f"{type_name}: ожидалось {expected_ratio:.2f}%, "
                        f"получено {actual_ratio:.2f}% (отклонение {deviation:.2f}%)"
                    )
            
            if type_errors:
                return {
                    'status': 'warning',
                    'message': '⚠️ Нарушены пропорции по типам магазинов',
                    'type_errors': type_errors,
                    'constant_selected': constant_selected_df,
                    'variable_selected': variable_selected_df,
                    'statistics': {
                        'constant_total': constant_total,
                        'constant_selected': len(constant_selected_df),
                        'constant_utilization': constant_utilization,
                        'variable_total': variable_total,
                        'variable_selected': len(variable_selected_df),
                        'variable_utilization': variable_utilization,
                        'total_selected': len(temp_ap)
                    }
                }
        
        # ==============================================
        # ШАГ 4: Проверка выполнения целевого объема
        # ==============================================
        current_count = len(temp_ap)
        
        if current_count < target_ap * (variable_threshold / 100):
            retro_selected_df = self._select_retro_points(
                retro_polygons, 
                target_ap - current_count,
                self.constant_df['Customer Name'].unique().tolist()
            )
        else:
            retro_selected_df = pd.DataFrame()
        
        # ==============================================
        # ШАГ 5: Формирование финальной АП
        # ==============================================
        final_ap = pd.concat([
            constant_selected_df,
            variable_selected_df,
            retro_selected_df
        ], ignore_index=True)
        
        final_ap = final_ap.drop_duplicates(subset=['Longitude', 'Latitude'])
        
        # ==============================================
        # ШАГ 6: Статистика
        # ==============================================
        final_count = len(final_ap)
        plan_completion = (final_count / target_ap * 100) if target_ap > 0 else 0
        
        utilization = {
            'constant': {
                'total': constant_total,
                'selected': len(constant_selected_df),
                'utilization': constant_utilization
            },
            'variable': {
                'total': variable_total,
                'selected': len(variable_selected_df),
                'utilization': variable_utilization
            },
            'retro': {
                'total': len(self.retro_df) if self.retro_df is not None else 0,
                'selected': len(retro_selected_df),
                'utilization': (len(retro_selected_df) / len(self.retro_df) * 100) if self.retro_df is not None and len(self.retro_df) > 0 else 0
            }
        }
        
        return {
            'status': 'success',
            'message': f'✅ План сформирован: {final_count} из {target_ap} ({plan_completion:.1f}%)',
            'final_ap': final_ap,
            'constant_selected': constant_selected_df,
            'variable_selected': variable_selected_df,
            'retro_selected': retro_selected_df,
            'statistics': {
                'target_ap': target_ap,
                'final_count': final_count,
                'plan_completion': plan_completion,
                'constant_total': constant_total,
                'constant_selected': len(constant_selected_df),
                'variable_total': variable_total,
                'variable_selected': len(variable_selected_df),
                'retro_selected': len(retro_selected_df),
                'constant_utilization': constant_utilization,
                'variable_utilization': variable_utilization
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
            if row['логин'] not in active_clients:
                continue
            
            if self.check_point_in_polygons(row['долгота'], row['широта'], retro_polygons):
                selected.append(row)
            
            if len(selected) >= needed_count:
                break
        
        return pd.DataFrame(selected)
