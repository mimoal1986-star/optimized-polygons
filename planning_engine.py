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
        Загружает три файла и преобразует координаты
        (запятая → точка, приведение к float)
        
        Args:
            constant_file: загруженный Excel-файл Константы
            variable_file: загруженный Excel-файл Переменной
            retro_file: загруженный Excel-файл Ретро
            
        Returns:
            bool: True если хотя бы Константа загружена
        """
        if constant_file is not None:
            self.constant_df = pd.read_excel(constant_file)
            # Заменяем запятые на точки в координатах
            self.constant_df['Latitude'] = self.constant_df['Latitude'].astype(str).str.replace(',', '.').astype(float)
            self.constant_df['Longitude'] = self.constant_df['Longitude'].astype(str).str.replace(',', '.').astype(float)
        
        if variable_file is not None:
            self.variable_df = pd.read_excel(variable_file)
            self.variable_df['Latitude'] = self.variable_df['Latitude'].astype(str).str.replace(',', '.').astype(float)
            self.variable_df['Longitude'] = self.variable_df['Longitude'].astype(str).str.replace(',', '.').astype(float)
        
        if retro_file is not None:
            self.retro_df = pd.read_excel(retro_file)
            self.retro_df['широта'] = self.retro_df['широта'].astype(str).str.replace(',', '.').astype(float)
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