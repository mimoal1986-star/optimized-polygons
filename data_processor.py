import pandas as pd
import json
import os
from datetime import datetime
import streamlit as st
import numpy as np

class DataProcessor:
    def __init__(self, data_file='data/auditor_data.json'):
        self.data_file = data_file
        self.data = self.load_data()
    
    def load_data(self):
        """Загрузка данных из JSON файла"""
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    def save_data(self):
        """Сохранение данных в JSON файл"""
        os.makedirs(os.path.dirname(self.data_file), exist_ok=True)
        with open(self.data_file, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
    
    def process_uploaded_file(self, uploaded_file):
        """Обработка загруженного Excel файла с векторизированными операциями"""
        try:
            # Чтение файла с оптимизацией
            df = pd.read_excel(
                uploaded_file,
                dtype=str,
                engine='openpyxl'
            )
            
            # Проверка наличия необходимых колонок
            required_cols = ['ТП', 'Дата визита', 'Гео/ш', 'Гео/д']
            missing_cols = [col for col in required_cols if col not in df.columns]
            if missing_cols:
                return None, f"Отсутствуют колонки: {', '.join(missing_cols)}"
            
            # Векторизированная фильтрация
            # 1. Удаляем пустые ТП
            df = df[df['ТП'].notna() & (df['ТП'] != '') & (df['ТП'] != 'nan')]
            
            # 2. Конвертируем координаты в числовой формат (векторизированно)
            df['lat'] = pd.to_numeric(df['Гео/ш'], errors='coerce')
            df['lon'] = pd.to_numeric(df['Гео/д'], errors='coerce')
            
            # 3. Удаляем строки с некорректными координатами
            df = df.dropna(subset=['lat', 'lon'])
            
            if df.empty:
                return None, "Нет данных с корректными координатами"
            
            # 4. Векторизированная обработка дат
            def parse_date(date_val):
                if pd.isna(date_val):
                    return None
                try:
                    if isinstance(date_val, str):
                        # Пробуем разные форматы
                        for fmt in ['%Y-%m-%d', '%d.%m.%Y', '%Y/%m/%d', '%d-%m-%Y']:
                            try:
                                return pd.to_datetime(date_val, format=fmt).strftime('%Y-%m-%d')
                            except:
                                continue
                    return pd.to_datetime(date_val).strftime('%Y-%m-%d')
                except:
                    return None
            
            df['visit_date'] = df['Дата визита'].apply(parse_date)
            df = df.dropna(subset=['visit_date'])
            
            if df.empty:
                return None, "Нет данных с корректными датами"
            
            # 5. Создание ключа (векторизированно)
            df['key'] = df['ТП'] + '_' + df['visit_date']
            
            # 6. Формирование данных в виде словаря (векторизированно)
            # Создаем базовый словарь из колонок
            new_data = {}
            
            # Получаем все колонки для сохранения
            all_cols = df.columns.tolist()
            
            # Векторизированное создание записей
            records = df.to_dict('records')
            
            for record in records:
                key = record['key']
                tp_id = str(record['ТП'])
                
                new_data[key] = {
                    'tp_id': tp_id,
                    'client_name': str(record.get('Имя клиента', '')) if pd.notna(record.get('Имя клиента', '')) else '',
                    'wave_id': str(record.get('ID волны', '')) if pd.notna(record.get('ID волны', '')) else '',
                    'wave_name': str(record.get('Название волны', '')) if pd.notna(record.get('Название волны', '')) else '',
                    'region': str(record.get('Регион', '')) if pd.notna(record.get('Регион', '')) else '',
                    'city': str(record.get('Город', '')) if pd.notna(record.get('Город', '')) else '',
                    'asm': str(record.get('АСМ', '')) if pd.notna(record.get('АСМ', '')) else '',
                    'em': str(record.get('ЭМ', '')) if pd.notna(record.get('ЭМ', '')) else '',
                    'auditor': tp_id,
                    'order_id': str(record.get('ID заказа', '')) if pd.notna(record.get('ID заказа', '')) else '',
                    'status': str(record.get('Статус', '')) if pd.notna(record.get('Статус', '')) else '',
                    'visit_date': record['visit_date'],
                    'request_date': str(record.get('Дата назначения запроса', '')) if pd.notna(record.get('Дата назначения запроса', '')) else '',
                    'rp': str(record.get('РП', '')) if pd.notna(record.get('РП', '')) else '',
                    'om': str(record.get('ОМ', '')) if pd.notna(record.get('ОМ', '')) else '',
                    'branch_id': str(record.get('ID филиала', '')) if pd.notna(record.get('ID филиала', '')) else '',
                    'branch_name': str(record.get('Полное название филиала', '')) if pd.notna(record.get('Полное название филиала', '')) else '',
                    'address': str(record.get('Адрес (город, адрес)', '')) if pd.notna(record.get('Адрес (город, адрес)', '')) else '',
                    'lat': float(record['lat']),
                    'lon': float(record['lon']),
                    'survey_id': str(record.get('ID обзора', '')) if pd.notna(record.get('ID обзора', '')) else '',
                    'project_code': str(record.get('код проекта', '')) if pd.notna(record.get('код проекта', '')) else ''
                }
            
            if not new_data:
                return None, "Не найдено валидных записей"
            
            # Объединение с существующими данными
            self.data.update(new_data)
            
            # Векторизированное удаление дубликатов 
            if self.data:
                temp_df = pd.DataFrame(self.data.values())
                
                if not temp_df.empty:
                    # Удаляем дубликаты по ТП + координаты (широта, долгота)
                    # Оставляем последнюю запись (самую новую по дате)
                    temp_df['visit_date_dt'] = pd.to_datetime(temp_df['visit_date'])
                    temp_df = temp_df.sort_values('visit_date_dt', ascending=False)
                    temp_df = temp_df.drop_duplicates(subset=['tp_id', 'lat', 'lon'], keep='first')
                    
                    # Конвертируем обратно в словарь
                    self.data = {}
                    for _, row in temp_df.iterrows():
                        key = f"{row['tp_id']}_{row['lat']}_{row['lon']}"
                        self.data[key] = row.to_dict()
                        # Преобразуем numpy типы в Python типы
                        for k, v in self.data[key].items():
                            if isinstance(v, (np.int64, np.float64)):
                                self.data[key][k] = v.item()
                            elif isinstance(v, pd.Timestamp):
                                self.data[key][k] = v.strftime('%Y-%m-%d')
                            elif isinstance(v, (np.bool_)):
                                self.data[key][k] = bool(v)
            
            self.save_data()
            
            return len(new_data), f"Успешно загружено {len(new_data)} новых записей"
            
        except Exception as e:
            return None, f"Ошибка при обработке файла: {str(e)}"
    
    def get_auditors(self):
        """Получить список всех аудиторов"""
        auditors = set()
        for record in self.data.values():
            auditor = record.get('auditor', '')
            if auditor and auditor != 'nan':
                auditors.add(auditor)
        return sorted(list(auditors))
    
    def get_data_by_auditor(self, auditor_id):
        """Получить данные по конкретному аудитору"""
        result = []
        for record in self.data.values():
            if record.get('auditor') == auditor_id:
                result.append(record)
        return result
    
    def get_statistics(self):
        """Получить статистику по данным"""
        stats = {
            'total_visits': len(self.data),
            'total_auditors': len(self.get_auditors()),
            'cities': set(),
            'regions': set()
        }
        for record in self.data.values():
            city = record.get('city', '')
            region = record.get('region', '')
            if city and city != 'nan':
                stats['cities'].add(city)
            if region and region != 'nan':
                stats['regions'].add(region)
        stats['cities'] = len(stats['cities'])
        stats['regions'] = len(stats['regions'])
        return stats

    def clear_data(self):
        """Очистить все данные"""
        self.data = {}
        self.save_data()
        return "Все данные удалены"
