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
    
    # Координаты центров городов-миллионников (широта, долгота)
    CITY_CENTERS = {
        'Волгоград': (48.7071, 44.5169),
        'Воронеж': (51.6605, 39.2003),
        'Екатеринбург': (56.8389, 60.6057),
        'Казань': (55.8304, 49.0661),
        'Краснодар': (45.0355, 38.9753),
        'Красноярск': (56.0106, 92.8526),
        'Москва': (55.7558, 37.6173),
        'Нижний Новгород': (56.2965, 43.9361),
        'Новосибирск': (55.0302, 82.9204),
        'Омск': (54.9885, 73.3242),
        'Пермь': (58.0104, 56.2294),
        'Ростов-на-Дону': (47.2357, 39.7015),
        'Самара': (53.1959, 50.1002),
        'Санкт-Петербург': (59.9343, 30.3351),
        'Уфа': (54.7388, 55.9721),
        'Челябинск': (55.1602, 61.4023),
    }
    
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
            
            # Запускаем автоматическую проверку координат
            errors, check_message = self.validate_coordinates()
            
            # Сохраняем ошибки в session_state для экспорта
            if errors:
                st.session_state['error_points'] = errors
            else:
                st.session_state['error_points'] = {}  # Очищаем старые ошибки
            
            return len(new_data), f"✅ Загружено {len(new_data)} записей (добавлено: {added_count}, обновлено: {updated_count}). {check_message}"
            
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

    def validate_coordinates(self):
        """
        Проверяет координаты всех точек:
        - Удаляет точки дальше 50 км от центра города
        - Возвращает словарь с ошибочными точками
        """
        import math
        if not self.data:
            return {}, "Нет данных для проверки"
        
        errors = {}
        
        for key, record in self.data.items():
            city = record.get('city', '')
            
            if city not in self.CITY_CENTERS:
                continue
            
            try:
                lon = float(record.get('lon', 0))
                lat = float(record.get('lat', 0))
                
                if lon == 0 or lat == 0:
                    errors[key] = record
                    continue
                
                center_lat, center_lon = self.CITY_CENTERS[city]
                
                # Расстояние по формуле гаверсинусов
                R = 6371
                lat1_rad = math.radians(center_lat)
                lat2_rad = math.radians(lat)
                delta_lat = math.radians(lat - center_lat)
                delta_lon = math.radians(lon - center_lon)
                
                a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon/2)**2
                c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
                distance = R * c
                
                if distance > 50:
                    errors[key] = record
                    
            except (ValueError, TypeError):
                errors[key] = record
        
        for key in errors:
            if key in self.data:
                del self.data[key]
        
        return errors, f"Проверка завершена. Удалено {len(errors)} ошибочных точек"

    def export_errors_to_excel(self, errors):
        """Создает Excel файл с ошибочными точками"""
        import io
        import pandas as pd
        
        if not errors:
            return None
        
        records = []
        for key, record in errors.items():
            row = {
                'ТП': record.get('tp_id', ''),
                'Дата визита': record.get('visit_date', ''),
                'Гео/ш': record.get('lat', ''),
                'Гео/д': record.get('lon', ''),
                'Город': record.get('city', ''),
                'Регион': record.get('region', ''),
                'Адрес (город, адрес)': record.get('address', ''),
            }
            records.append(row)
        
        df = pd.DataFrame(records)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Ошибочные точки', index=False)
        
        output.seek(0)
        return output.getvalue()

    def get_points_by_city(self, auditor_id):
        """
        Группирует точки аудитора по городам
        Возвращает: {город: [(lon, lat), ...]}
        """
        records = self.get_data_by_auditor(auditor_id)
        
        cities = {}
        for record in records:
            city = record.get('city', 'Неизвестно')
            if city not in cities:
                cities[city] = []
            try:
                lon = float(record['lon'])
                lat = float(record['lat'])
                cities[city].append((lon, lat))
            except (ValueError, TypeError):
                continue
        
        return cities
