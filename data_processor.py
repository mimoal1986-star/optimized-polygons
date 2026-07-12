import pandas as pd
import json
import os
from datetime import datetime
import streamlit as st
import numpy as np
import requests
import base64

class DataProcessor:
    def __init__(self):
        """Инициализация с GitHub API"""
        # Проверяем наличие секретов
        if 'github' not in st.secrets:
            st.error("❌ Секреты GitHub не найдены. Добавьте их в Streamlit Secrets")
            self.available = False
            self.data = {}
            return
        
        # GitHub настройки из секретов
        self.token = st.secrets['github']['token']
        self.repo = st.secrets['github']['repo']
        self.branch = st.secrets['github']['branch']
        self.file_path = 'auditor_data.json'
        
        # URL для GitHub API
        self.api_url = f"https://api.github.com/repos/{self.repo}/contents/{self.file_path}"
        self.headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        self.available = True
        self.data = self.load_data()
    
    def _get_file_sha(self):
        """Получает SHA текущего файла (нужен для обновления)"""
        if not self.available:
            return None
        try:
            response = requests.get(
                self.api_url,
                headers=self.headers,
                params={"ref": self.branch}
            )
            if response.status_code == 200:
                return response.json()["sha"]
            return None
        except Exception:
            return None
    
    def load_data(self):
        """Загрузка данных из GitHub"""
        if not self.available:
            return {}
        
        try:
            response = requests.get(
                self.api_url,
                headers=self.headers,
                params={"ref": self.branch}
            )
            
            if response.status_code == 200:
                content = response.json()
                file_content = base64.b64decode(content["content"]).decode("utf-8")
                return json.loads(file_content)
            else:
                # Если файла нет, возвращаем пустой словарь
                return {}
                
        except Exception as e:
            st.warning(f"Не удалось загрузить данные: {e}")
            return {}
    
    def save_data(self):
        """Сохранение данных в GitHub"""
        if not self.available:
            return False, "❌ GitHub не доступен"
        
        try:
            # Конвертируем в JSON
            content = json.dumps(self.data, indent=2, ensure_ascii=False)
            content_base64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")
            
            # Получаем SHA для обновления
            sha = self._get_file_sha()
            
            # Формируем запрос
            payload = {
                "message": f"Обновление данных аудиторов от {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                "content": content_base64,
                "branch": self.branch
            }
            if sha:
                payload["sha"] = sha
            
            response = requests.put(
                self.api_url,
                headers=self.headers,
                json=payload
            )
            
            if response.status_code in [200, 201]:
                return True, f"✅ Данные сохранены в GitHub ({len(self.data)} записей)"
            else:
                return False, f"❌ Ошибка сохранения: {response.status_code}"
                
        except Exception as e:
            return False, f"❌ Ошибка: {str(e)}"
    
    def process_uploaded_file(self, uploaded_file):
        """Обработка загруженного Excel файла (без автосохранения)"""
        try:
            df = pd.read_excel(uploaded_file, dtype=str, engine='openpyxl')
            
            required_cols = ['ТП', 'Дата визита', 'Гео/ш', 'Гео/д']
            missing_cols = [col for col in required_cols if col not in df.columns]
            if missing_cols:
                return None, f"Отсутствуют колонки: {', '.join(missing_cols)}"
            
            # Фильтрация
            df = df[df['ТП'].notna() & (df['ТП'] != '') & (df['ТП'] != 'nan')]
            
            # Координаты
            df['lat'] = pd.to_numeric(df['Гео/ш'], errors='coerce')
            df['lon'] = pd.to_numeric(df['Гео/д'], errors='coerce')
            df = df.dropna(subset=['lat', 'lon'])
            
            if df.empty:
                return None, "Нет данных с корректными координатами"
            
            # Даты
            def parse_date(date_val):
                if pd.isna(date_val):
                    return None
                try:
                    if isinstance(date_val, str):
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
            
            # Ключ = ТП + координаты
            df['key'] = df['ТП'] + '_' + df['lat'].astype(str) + '_' + df['lon'].astype(str)
            
            # Формирование данных
            new_data = {}
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
            
            # Обогащение данных (добавление новых полей, а не замена)
            added_count = 0
            updated_count = 0
            for key, new_record in new_data.items():
                if key in self.data:
                    # Обогащаем существующую запись
                    for field, value in new_record.items():
                        if value and value != '' and value != 'nan':
                            self.data[key][field] = value
                    updated_count += 1
                else:
                    # Добавляем новую запись
                    self.data[key] = new_record
                    added_count += 1
            
            return len(new_data), f"✅ Загружено {len(new_data)} записей (добавлено: {added_count}, обновлено: {updated_count})"
            
        except Exception as e:
            return None, f"Ошибка при обработке файла: {str(e)}"
    
    def get_auditors(self):
        auditors = set()
        for record in self.data.values():
            auditor = record.get('auditor', '')
            if auditor and auditor != 'nan':
                auditors.add(auditor)
        return sorted(list(auditors))
    
    def get_data_by_auditor(self, auditor_id):
        result = []
        for record in self.data.values():
            if record.get('auditor') == auditor_id:
                result.append(record)
        return result
    
    def get_statistics(self):
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
        self.data = {}
        success, message = self.save_data()
        return f"Все данные удалены. {message}"
