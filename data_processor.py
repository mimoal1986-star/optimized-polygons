import pandas as pd
import json
import os
from datetime import datetime
import streamlit as st
import numpy as np
import requests
import base64
import uuid

class DataProcessor:
    def __init__(self):
        """Инициализация с GitHub API"""
        if 'github' not in st.secrets:
            st.error("❌ Секреты GitHub не найдены. Добавьте их в Streamlit Secrets")
            self.available = False
            self.data = {}
            return
        
        self.token = st.secrets['github']['token']
        self.repo = st.secrets['github']['repo']
        self.branch = st.secrets['github']['branch']
        self.file_path = 'auditor_data.json'
        
        self.api_url = f"https://api.github.com/repos/{self.repo}/contents/{self.file_path}"
        self.headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        self.available = True
        self.data = self.load_data()
    
    def _get_file_sha(self):
        """Получает SHA текущего файла"""
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
                
                if not file_content or file_content.strip() == '':
                    print("⚠️ Файл пустой, возвращаем пустой словарь")
                    return {}
                
                try:
                    return json.loads(file_content)
                except json.JSONDecodeError as e:
                    print(f"❌ Ошибка парсинга JSON: {e}")
                    return {}
            return {}
                
        except Exception as e:
            st.warning(f"Не удалось загрузить данные: {e}")
            return {}
    
    def save_data(self):
        """Сохранение данных в GitHub с пересчетом номеров"""
        if not self.available:
            return False, "❌ GitHub не доступен"
        
        try:
            data_list = list(self.data.values())
            for i, record in enumerate(data_list, 1):
                record['record_number'] = i
                record['record_updated'] = datetime.now().isoformat()
            
            self.data = {}
            for record in data_list:
                key = f"{record['tp_id']}_{record['visit_date']}_{record['lat']}_{record['lon']}"
                self.data[key] = record
            
            content = json.dumps(self.data, indent=2, ensure_ascii=False)
            content_base64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")
            
            sha = self._get_file_sha()
            
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
            
            if response.status_code == 409:
                print("⚠️ Конфликт при сохранении, пробуем обновить SHA...")
                new_sha = self._get_file_sha()
                if new_sha:
                    payload["sha"] = new_sha
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
        """Обработка загруженного Excel файла"""
        if uploaded_file is None:
            return None, "Файл не выбран"
        
        try:
            df = pd.read_excel(uploaded_file, dtype=str, engine='openpyxl')
            
            required_cols = ['ТП', 'Дата визита', 'Гео/ш', 'Гео/д']
            missing_cols = [col for col in required_cols if col not in df.columns]
            if missing_cols:
                return None, f"Отсутствуют колонки: {', '.join(missing_cols)}"
            
            df = df[df['ТП'].notna() & (df['ТП'] != '') & (df['ТП'] != 'nan')]
            
            df['lat'] = pd.to_numeric(df['Гео/ш'], errors='coerce')
            df['lon'] = pd.to_numeric(df['Гео/д'], errors='coerce')
            df = df.dropna(subset=['lat', 'lon'])
            
            if df.empty:
                return None, "Нет данных с корректными координатами"
            
            df['visit_date'] = pd.to_datetime(
                df['Дата визита'], 
                errors='coerce'
            ).dt.strftime('%Y-%m-%d')
            df = df.dropna(subset=['visit_date'])
            
            if df.empty:
                return None, "Нет данных с корректными датами"
            
            df['key'] = (
                df['ТП'] + '_' + 
                df['visit_date'] + '_' + 
                df['lat'].astype(str) + '_' + 
                df['lon'].astype(str)
            )
            
            df = df.drop_duplicates(subset=['key'], keep='first')
            
            new_data = {}
            records = df.to_dict('records')
            
            for record in records:
                key = record['key']
                tp_id = str(record['ТП'])
                
                new_data[key] = {
                    'record_id': str(uuid.uuid4()),
                    'record_created': datetime.now().isoformat(),
                    'tp_id': tp_id,
                    'auditor': tp_id,
                    'city': str(record.get('Город', '')) if pd.notna(record.get('Город', '')) else '',
                    'region': str(record.get('Регион', '')) if pd.notna(record.get('Регион', '')) else '',
                    'address': str(record.get('Адрес (город, адрес)', '')) if pd.notna(record.get('Адрес (город, адрес)', '')) else '',
                    'visit_date': record['visit_date'],
                    'lat': float(record['lat']),
                    'lon': float(record['lon'])
                }
            
            if not new_data:
                return None, "Не найдено валидных записей"
            
            added_count = 0
            updated_count = 0
            
            for key, new_record in new_data.items():
                if key in self.data:
                    for field, value in new_record.items():
                        if value and value != '' and value != 'nan':
                            self.data[key][field] = value
                    updated_count += 1
                else:
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

    def get_statistics_from_json(self):
    """Загрузка статистики напрямую из JSON файла"""
    data = self.load_data()
    if not data:
        return {
            'total_visits': 0,
            'total_auditors': 0,
            'cities': 0,
            'regions': 0
        }
    
    auditors = set()
    cities = set()
    regions = set()
    
    for record in data.values():
        auditor = record.get('auditor', '')
        if auditor and auditor != 'nan':
            auditors.add(auditor)
        
        city = record.get('city', '')
        if city and city != 'nan':
            cities.add(city)
        
        region = record.get('region', '')
        if region and region != 'nan':
            regions.add(region)
    
    return {
        'total_visits': len(data),
        'total_auditors': len(auditors),
        'cities': len(cities),
        'regions': len(regions)
    }

    def clear_data(self):
        self.data = {}
        success, message = self.save_data()
        return f"Все данные удалены. {message}"
