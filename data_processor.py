import pandas as pd
import json
import os
from datetime import datetime
import streamlit as st

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
        """Обработка загруженного Excel файла"""
        try:
            df = pd.read_excel(uploaded_file)
            
            # Проверка наличия необходимых колонок
            required_cols = ['ТП', 'Дата визита', 'Гео/ш', 'Гео/д']
            missing_cols = [col for col in required_cols if col not in df.columns]
            if missing_cols:
                return None, f"Отсутствуют колонки: {', '.join(missing_cols)}"
            
            # Извлечение данных
            new_data = {}
            for _, row in df.iterrows():
                tp_id = str(row.get('ТП', ''))
                if pd.isna(tp_id) or tp_id == '' or tp_id == 'nan':
                    continue
                
                # Проверка координат
                lat = row.get('Гео/ш')
                lon = row.get('Гео/д')
                if pd.isna(lat) or pd.isna(lon):
                    continue
                
                # Проверка, что координаты - числа
                try:
                    lat = float(lat)
                    lon = float(lon)
                except (ValueError, TypeError):
                    continue
                
                # Создание ключа для уникальности (ТП + дата)
                visit_date = row.get('Дата визита')
                if pd.isna(visit_date):
                    continue
                    
                if isinstance(visit_date, pd.Timestamp):
                    visit_date = visit_date.strftime('%Y-%m-%d')
                elif isinstance(visit_date, datetime):
                    visit_date = visit_date.strftime('%Y-%m-%d')
                elif isinstance(visit_date, str):
                    # Попытка парсинга даты из строки
                    try:
                        date_obj = pd.to_datetime(visit_date)
                        visit_date = date_obj.strftime('%Y-%m-%d')
                    except:
                        visit_date = str(visit_date)
                else:
                    visit_date = str(visit_date)
                
                key = f"{tp_id}_{visit_date}"
                
                # Собираем все данные
                new_data[key] = {
                    'tp_id': tp_id,
                    'client_name': str(row.get('Имя клиента', '')) if not pd.isna(row.get('Имя клиента', '')) else '',
                    'wave_id': str(row.get('ID волны', '')) if not pd.isna(row.get('ID волны', '')) else '',
                    'wave_name': str(row.get('Название волны', '')) if not pd.isna(row.get('Название волны', '')) else '',
                    'region': str(row.get('Регион', '')) if not pd.isna(row.get('Регион', '')) else '',
                    'city': str(row.get('Город', '')) if not pd.isna(row.get('Город', '')) else '',
                    'asm': str(row.get('АСМ', '')) if not pd.isna(row.get('АСМ', '')) else '',
                    'em': str(row.get('ЭМ', '')) if not pd.isna(row.get('ЭМ', '')) else '',
                    'auditor': str(row.get('ТП', '')) if not pd.isna(row.get('ТП', '')) else '',
                    'order_id': str(row.get('ID заказа', '')) if not pd.isna(row.get('ID заказа', '')) else '',
                    'status': str(row.get('Статус', '')) if not pd.isna(row.get('Статус', '')) else '',
                    'visit_date': visit_date,
                    'request_date': str(row.get('Дата назначения запроса', '')) if not pd.isna(row.get('Дата назначения запроса', '')) else '',
                    'rp': str(row.get('РП', '')) if not pd.isna(row.get('РП', '')) else '',
                    'om': str(row.get('ОМ', '')) if not pd.isna(row.get('ОМ', '')) else '',
                    'branch_id': str(row.get('ID филиала', '')) if not pd.isna(row.get('ID филиала', '')) else '',
                    'branch_name': str(row.get('Полное название филиала', '')) if not pd.isna(row.get('Полное название филиала', '')) else '',
                    'address': str(row.get('Адрес (город, адрес)', '')) if not pd.isna(row.get('Адрес (город, адрес)', '')) else '',
                    'lat': lat,
                    'lon': lon,
                    'survey_id': str(row.get('ID обзора', '')) if not pd.isna(row.get('ID обзора', '')) else '',
                    'project_code': str(row.get('код проекта', '')) if not pd.isna(row.get('код проекта', '')) else ''
                }
            
            if not new_data:
                return None, "Не найдено валидных записей с координатами"
            
            # Объединение с существующими данными (удаление дубликатов)
            self.data.update(new_data)
            
            # Удаление дубликатов (оставляем последнюю запись)
            unique_data = {}
            for key, value in self.data.items():
                # Если ключ уже существует, обновляем
                if key not in unique_data:
                    unique_data[key] = value
                else:
                    # Если дубликат, обновляем датой
                    if value['visit_date'] > unique_data[key]['visit_date']:
                        unique_data[key] = value
            
            self.data = unique_data
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