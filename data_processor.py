import pandas as pd
import json
import os
from datetime import datetime, timedelta
import streamlit as st
import numpy as np
import requests
import base64
import uuid
import time
from typing import Dict, List, Optional
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DataValidator:
    """Класс для валидации данных"""
    
    @staticmethod
    def validate_coordinates(lat: float, lon: float) -> bool:
        """Проверка валидности координат"""
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            return False
        if not (-90 <= lat <= 90):
            logger.warning(f"Широта {lat} вне диапазона [-90, 90]")
            return False
        if not (-180 <= lon <= 180):
            logger.warning(f"Долгота {lon} вне диапазона [-180, 180]")
            return False
        return True
    
    @staticmethod
    def validate_date(date_str: str) -> bool:
        """Проверка валидности даты"""
        try:
            pd.to_datetime(date_str)
            return True
        except:
            return False
    
    @staticmethod
    def deduplicate_points(points: List[tuple], tolerance: float = 0.0001) -> List[tuple]:
        """Удаление почти дублирующихся точек"""
        if not points:
            return points
        
        unique = []
        for point in points:
            is_duplicate = False
            for existing in unique:
                if (abs(point[0] - existing[0]) < tolerance and 
                    abs(point[1] - existing[1]) < tolerance):
                    is_duplicate = True
                    break
            if not is_duplicate:
                unique.append(point)
        
        logger.info(f"Дедупликация: {len(points)} -> {len(unique)} точек")
        return unique

class GitHubStorage:
    """Класс для работы с GitHub Storage"""
    
    def __init__(self, token: str, repo: str, branch: str, file_path: str = 'auditor_data.json'):
        self.token = token
        self.repo = repo
        self.branch = branch
        self.file_path = file_path
        self.api_url = f"https://api.github.com/repos/{self.repo}/contents/{self.file_path}"
        self.headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json"
        }
        self.max_retries = 5
        self.backup_dir = 'backups'
        os.makedirs(self.backup_dir, exist_ok=True)
    
    def _get_file_sha(self) -> Optional[str]:
        """Получает SHA текущего файла с ретраями"""
        for attempt in range(self.max_retries):
            try:
                response = requests.get(
                    self.api_url,
                    headers=self.headers,
                    params={"ref": self.branch},
                    timeout=10
                )
                if response.status_code == 200:
                    return response.json().get("sha")
                elif response.status_code == 404:
                    return None
                else:
                    logger.warning(f"Ошибка получения SHA: {response.status_code}, попытка {attempt+1}")
                    time.sleep(2 ** attempt)
            except Exception as e:
                logger.error(f"Ошибка получения SHA: {e}")
                if attempt == self.max_retries - 1:
                    raise
                time.sleep(2 ** attempt)
        return None
    
    def load(self) -> Dict:
        """Загрузка данных с GitHub"""
        for attempt in range(self.max_retries):
            try:
                response = requests.get(
                    self.api_url,
                    headers=self.headers,
                    params={"ref": self.branch},
                    timeout=10
                )
                
                if response.status_code == 200:
                    content = response.json()
                    file_content = base64.b64decode(content["content"]).decode("utf-8")
                    
                    if not file_content or file_content.strip() == '':
                        logger.info("Файл пустой, возвращаем пустой словарь")
                        return {}
                    
                    try:
                        data = json.loads(file_content)
                        logger.info(f"Загружено {len(data)} записей из GitHub")
                        return data
                    except json.JSONDecodeError as e:
                        logger.error(f"Ошибка парсинга JSON: {e}")
                        backup_data = self._load_latest_backup()
                        if backup_data:
                            logger.info("Загружены данные из бэкапа")
                            return backup_data
                        return {}
                elif response.status_code == 404:
                    logger.info("Файл не найден, создаем новый")
                    return {}
                else:
                    logger.warning(f"Ошибка загрузки: {response.status_code}, попытка {attempt+1}")
                    time.sleep(2 ** attempt)
            except Exception as e:
                logger.error(f"Ошибка загрузки: {e}")
                if attempt == self.max_retries - 1:
                    backup_data = self._load_latest_backup()
                    if backup_data:
                        logger.info("Загружены данные из бэкапа")
                        return backup_data
                    raise
                time.sleep(2 ** attempt)
        
        return {}
    
    def save(self, data: Dict) -> tuple:
        """Сохранение данных с обработкой конфликтов"""
        for attempt in range(self.max_retries):
            try:
                sha = self._get_file_sha()
                
                content = json.dumps(data, indent=2, ensure_ascii=False)
                content_base64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")
                
                payload = {
                    "message": f"Обновление данных от {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    "content": content_base64,
                    "branch": self.branch
                }
                if sha:
                    payload["sha"] = sha
                
                response = requests.put(
                    self.api_url,
                    headers=self.headers,
                    json=payload,
                    timeout=10
                )
                
                if response.status_code in [200, 201]:
                    self._create_backup(data)
                    logger.info(f"Данные сохранены, {len(data)} записей")
                    return True, f"✅ Сохранено {len(data)} записей"
                
                elif response.status_code == 409:
                    logger.warning(f"Конфликт при сохранении, попытка {attempt+1}")
                    fresh_data = self.load()
                    merged_data = self._merge_data(fresh_data, data)
                    
                    content = json.dumps(merged_data, indent=2, ensure_ascii=False)
                    content_base64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")
                    
                    new_sha = self._get_file_sha()
                    payload = {
                        "message": f"Слияние данных от {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                        "content": content_base64,
                        "branch": self.branch,
                        "sha": new_sha
                    }
                    
                    response = requests.put(
                        self.api_url,
                        headers=self.headers,
                        json=payload,
                        timeout=10
                    )
                    
                    if response.status_code in [200, 201]:
                        self._create_backup(merged_data)
                        logger.info(f"Данные слиты и сохранены, {len(merged_data)} записей")
                        return True, f"✅ Сохранено {len(merged_data)} записей (конфликт разрешен)"
                    
                else:
                    logger.error(f"Ошибка сохранения: {response.status_code}")
                    if attempt == self.max_retries - 1:
                        return False, f"❌ Ошибка сохранения: {response.status_code}"
                
                time.sleep(2 ** attempt)
                
            except Exception as e:
                logger.error(f"Ошибка сохранения: {e}")
                if attempt == self.max_retries - 1:
                    return False, f"❌ Ошибка: {str(e)}"
                time.sleep(2 ** attempt)
        
        return False, "❌ Превышено количество попыток"
    
    def _merge_data(self, base_data: Dict, new_data: Dict) -> Dict:
        """Слияние данных"""
        merged = base_data.copy()
        
        for key, value in new_data.items():
            if key in merged:
                for field, val in value.items():
                    if val and val != '' and val != 'nan':
                        merged[key][field] = val
                merged[key]['record_updated'] = datetime.now().isoformat()
            else:
                merged[key] = value
        
        logger.info(f"Слияние: {len(base_data)} -> {len(merged)} записей")
        return merged
    
    def _create_backup(self, data: Dict):
        """Создание локального бэкапа"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_file = os.path.join(self.backup_dir, f'auditor_data_backup_{timestamp}.json')
            
            with open(backup_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            self._cleanup_old_backups(keep=10)
            
            logger.info(f"Создан бэкап: {backup_file}")
        except Exception as e:
            logger.error(f"Ошибка создания бэкапа: {e}")
    
    def _load_latest_backup(self) -> Optional[Dict]:
        """Загрузка последнего бэкапа"""
        try:
            backup_files = [f for f in os.listdir(self.backup_dir) if f.startswith('auditor_data_backup_')]
            if not backup_files:
                return None
            
            latest_file = sorted(backup_files)[-1]
            backup_path = os.path.join(self.backup_dir, latest_file)
            
            with open(backup_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            logger.info(f"Загружен бэкап: {latest_file}, {len(data)} записей")
            return data
        except Exception as e:
            logger.error(f"Ошибка загрузки бэкапа: {e}")
            return None
    
    def _cleanup_old_backups(self, keep: int = 10):
        """Удаление старых бэкапов"""
        try:
            backup_files = [f for f in os.listdir(self.backup_dir) if f.startswith('auditor_data_backup_')]
            if len(backup_files) > keep:
                files_to_delete = sorted(backup_files)[:-keep]
                for file in files_to_delete:
                    os.remove(os.path.join(self.backup_dir, file))
                    logger.info(f"Удален старый бэкап: {file}")
        except Exception as e:
            logger.error(f"Ошибка очистки бэкапов: {e}")
    
    def create_backup_copy(self) -> tuple:
        """Создание копии текущих данных"""
        try:
            data = self.load()
            if not data:
                return False, "Нет данных для бэкапа"
            
            self._create_backup(data)
            return True, f"✅ Бэкап создан: {len(data)} записей"
        except Exception as e:
            return False, f"❌ Ошибка бэкапа: {str(e)}"

class DataProcessor:
    def __init__(self):
        """Инициализация с GitHub API"""
        if 'github' not in st.secrets:
            st.error("❌ Секреты GitHub не найдены")
            self.available = False
            self.data = {}
            return
        
        try:
            self.storage = GitHubStorage(
                token=st.secrets['github']['token'],
                repo=st.secrets['github']['repo'],
                branch=st.secrets['github']['branch']
            )
            
            self.available = True
            self.data = self.storage.load()
            self.validator = DataValidator()
            
            logger.info(f"DataProcessor инициализирован, {len(self.data)} записей")
            
        except Exception as e:
            st.error(f"❌ Ошибка инициализации: {str(e)}")
            self.available = False
            self.data = {}
    
    def load_data(self) -> Dict:
        """Загрузка данных"""
        if not self.available:
            return {}
        
        try:
            self.data = self.storage.load()
            return self.data
        except Exception as e:
            logger.error(f"Ошибка загрузки: {e}")
            return self.data
    
    def save_data(self) -> tuple:
        """Сохранение данных"""
        if not self.available:
            return False, "❌ GitHub не доступен"
        
        data_list = list(self.data.values())
        for i, record in enumerate(data_list, 1):
            record['record_number'] = i
            record['record_updated'] = datetime.now().isoformat()
        
        self.data = {}
        for record in data_list:
            key = f"{record['tp_id']}_{record.get('visit_date', '')}_{record.get('lat', '')}_{record.get('lon', '')}"
            self.data[key] = record
        
        return self.storage.save(self.data)
    
    def create_backup(self) -> tuple:
        """Создание бэкапа"""
        if not self.available:
            return False, "❌ GitHub не доступен"
        return self.storage.create_backup_copy()
    
    def process_uploaded_file(self, uploaded_file):
        """Обработка загруженного Excel файла"""
        if uploaded_file is None:
            return None, "Файл не выбран"
        
        try:
            df = pd.read_excel(uploaded_file, dtype=str, engine='openpyxl')
            
            required_cols = ['ТП', 'Дата визита', 'Гео/ш', 'Гео/д']
            missing_cols = [col for col in required_cols if col not in df.columns]
            
            if missing_cols:
                alt_cols = {
                    'ТП': ['ТП', 'Торговая точка', 'TP'],
                    'Дата визита': ['Дата визита', 'Дата', 'Visit date'],
                    'Гео/ш': ['Гео/ш', 'Широта', 'Latitude', 'Lat'],
                    'Гео/д': ['Гео/д', 'Долгота', 'Longitude', 'Lon']
                }
                
                mapping = {}
                for required, alternatives in alt_cols.items():
                    for alt in alternatives:
                        if alt in df.columns:
                            mapping[required] = alt
                            break
                
                if len(mapping) == len(required_cols):
                    df = df.rename(columns={v: k for k, v in mapping.items()})
                    logger.info(f"Колонки переименованы: {mapping}")
                else:
                    return None, f"Отсутствуют колонки: {', '.join(missing_cols)}"
            
            df = df[df['ТП'].notna() & (df['ТП'] != '') & (df['ТП'] != 'nan')]
            
            df['lat'] = pd.to_numeric(df['Гео/ш'], errors='coerce')
            df['lon'] = pd.to_numeric(df['Гео/д'], errors='coerce')
            
            valid_mask = df.apply(
                lambda row: self.validator.validate_coordinates(row['lat'], row['lon']), 
                axis=1
            )
            df = df[valid_mask]
            
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
                
                new_data[key] = {
                    'record_id': str(uuid.uuid4()),
                    'record_created': datetime.now().isoformat(),
                    'tp_id': str(record['ТП']),
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
                    self.data[key]['record_updated'] = datetime.now().isoformat()
                    updated_count += 1
                else:
                    self.data[key] = new_record
                    added_count += 1
            
            logger.info(f"Загружено {len(new_data)} записей (добавлено: {added_count}, обновлено: {updated_count})")
            
            return len(new_data), f"✅ Загружено {len(new_data)} записей (добавлено: {added_count}, обновлено: {updated_count})"
            
        except Exception as e:
            logger.error(f"Ошибка обработки файла: {str(e)}", exc_info=True)
            return None, f"Ошибка при обработке файла: {str(e)}"
    
    def get_auditors(self) -> List[str]:
        """Получение списка аудиторов"""
        auditors = set()
        for record in self.data.values():
            auditor = record.get('auditor', '')
            if auditor and auditor != 'nan':
                auditors.add(auditor)
        return sorted(list(auditors))
    
    def get_data_by_auditor(self, auditor_id: str) -> List[Dict]:
        """Получение данных по аудитору"""
        result = []
        for record in self.data.values():
            if record.get('auditor') == auditor_id:
                result.append(record)
        return result
    
    def get_statistics_from_json(self) -> Dict:
        """Получение статистики"""
        data = self.data if self.data else self.load_data()
        
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
    
    def clear_data(self) -> str:
        """Очистка данных"""
        self.data = {}
        success, message = self.save_data()
        if success:
            logger.info("Данные очищены")
            return f"✅ Данные очищены. {message}"
        else:
            return f"❌ Ошибка очистки: {message}"
