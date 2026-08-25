import pandas as pd
import streamlit as st
from shapely.geometry import Point, Polygon
from shapely.prepared import prep
from shapely.strtree import STRtree
from typing import Dict, Tuple, Optional, Set
import numpy as np
from functools import lru_cache

class PlanningEngine:
    """
    Класс для формирования плана визитов (АП)
    ОПТИМИЗИРОВАННАЯ ВЕРСИЯ 2.0
    - Векторизация операций
    - R-Tree индекс для быстрой проверки точек в полигонах
    - Кеширование результатов
    - Пакетное добавление точек
    - Адаптивный выбор стратегии
    """
    
    def __init__(self):
        self.client_ratios = {}
        self.type_ratios = {}
        self.constant_df = None
        self.variable_df = None
        self.retro_df = None
        self._polygon_cache = None
        self._rtree = None
        self._polygon_ids_by_geom = {}
        self._polygon_auditors_by_geom = {}
        self._use_rtree = False
        
    def load_files(self, constant_file, variable_file, retro_file):
        """Загружает три файла с оптимизациями"""
        
        def normalize_city_name(city):
            if pd.isna(city) or city == '':
                return ''
            return str(city).strip().lower().title()
        
        def validate_coordinates(df, source_name):
            """Проверяет наличие координат в DataFrame (без изменения)"""
            if df is None or df.empty:
                return False, f"Файл {source_name} пустой", df
            
            if 'Longitude' not in df.columns or 'Latitude' not in df.columns:
                return False, f"В {source_name} отсутствуют колонки Longitude/Latitude", df
            
            try:
                test_df = df.copy()
                test_df['Longitude'] = test_df['Longitude'].astype(str).str.replace(',', '.').astype(float)
                test_df['Latitude'] = test_df['Latitude'].astype(str).str.replace(',', '.').astype(float)
            except Exception as e:
                return False, f"В {source_name} координаты содержат нечисловые значения: {str(e)}", df
            
            return True, "OK", test_df
        
        # Константа
        if constant_file is not None:
            self.constant_df = pd.read_excel(constant_file)
            
            is_valid, msg, validated_df = validate_coordinates(self.constant_df, "Константе")
            if not is_valid:
                st.error(f"❌ Ошибка в Константе: {msg}")
                self.constant_df = None
                return False
            
            self.constant_df = validated_df
            
            required_cols = ['Город', 'RED PoS Group', 'Сеть']
            missing_cols = [col for col in required_cols if col not in self.constant_df.columns]
            if missing_cols:
                st.error(f"❌ В Константе отсутствуют колонки: {', '.join(missing_cols)}")
                self.constant_df = None
                return False
            
            if 'Город' in self.constant_df.columns:
                self.constant_df['Город'] = self.constant_df['Город'].apply(normalize_city_name)
            
            self.type_ratios = self.calculate_type_ratios()
            self.client_ratios = self.calculate_client_ratios()
        
        # Переменная
        if variable_file is not None:
            self.variable_df = pd.read_excel(variable_file)
            
            if self.variable_df.empty:
                st.warning("⚠️ Файл Переменной пустой!")
                self.variable_df = None
            else:
                is_valid, msg, validated_df = validate_coordinates(self.variable_df, "Переменной")
                if not is_valid:
                    st.error(f"❌ Ошибка в Переменной: {msg}")
                    self.variable_df = None
                else:
                    self.variable_df = validated_df
                    if 'Город' in self.variable_df.columns:
                        self.variable_df['Город'] = self.variable_df['Город'].apply(normalize_city_name)
        
        # Ретро
        if retro_file is not None:
            self.retro_df = pd.read_excel(retro_file)
            
            if self.retro_df.empty:
                st.warning("⚠️ Файл Ретро пустой!")
                self.retro_df = None
            else:
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
                
                is_valid, msg, validated_df = validate_coordinates(self.retro_df, "Ретро")
                if not is_valid:
                    st.error(f"❌ Ошибка в Ретро: {msg}")
                    self.retro_df = None
                else:
                    self.retro_df = validated_df
                    if 'Город' in self.retro_df.columns:
                        self.retro_df['Город'] = self.retro_df['Город'].apply(normalize_city_name)
        
        return self.constant_df is not None
    
    @lru_cache(maxsize=128)
    def _get_city_ratios_cached(self):
        """Кешированный расчёт пропорций по городам"""
        return self.calculate_city_ratios()
    
    def calculate_client_ratios(self):
        if self.constant_df is None or self.constant_df.empty:
            return {}
        
        total_rows = len(self.constant_df)
        client_counts = self.constant_df['Сеть'].value_counts()
        return {client: (count / total_rows * 100) for client, count in client_counts.items()}
    
    def calculate_city_ratios(self):
        if self.constant_df is None or self.constant_df.empty:
            return {}
        
        total_rows = len(self.constant_df)
        city_counts = self.constant_df['Город'].value_counts()
        return {city: (count / total_rows * 100) for city, count in city_counts.items()}

    def calculate_type_ratios(self):
        if self.constant_df is None or self.constant_df.empty:
            return {}
        
        total_rows = len(self.constant_df)
        type_counts = self.constant_df['RED PoS Group'].value_counts()
        
        return {
            type_name: (count / total_rows * 100) 
            for type_name, count in type_counts.items() 
            if type_name and type_name != 'nan'
        }

    def calculate_score_v2(self, point, type_counts, client_counts, total,
                          type_ratios, client_ratios,
                          bonus_type=6, bonus_proximity=5, bonus_client=4):
        """
        Расчёт Score точки на основе:
        1. Тип магазина (бонус)
        2. Клиент (бонус)
        3. Близость к Константе (добавляется отдельно)
        
        type_counts и client_counts передаются готовыми (ускорение!)
        """
        score = 0
        
        # 1. Тип магазина (используем готовые type_counts)
        if bonus_type > 0 and 'RED PoS Group' in point and type_ratios:
            point_type = point['RED PoS Group']
            if point_type in type_ratios:
                current_count = type_counts.get(point_type, 0)
                current_ratio = (current_count / total * 100) if total > 0 else 0
                expected_ratio = type_ratios[point_type]
                
                if expected_ratio > 0 and current_ratio < expected_ratio:
                    shortage = expected_ratio - current_ratio
                    bonus_multiplier = min(1.0, shortage / 10)
                    score += int(bonus_type * bonus_multiplier)
        
        # 2. Клиент (используем готовые client_counts)
        if bonus_client > 0 and 'Сеть' in point and client_ratios:
            point_client = point['Сеть']
            if point_client in client_ratios:
                current_count = client_counts.get(point_client, 0)
                current_ratio = (current_count / total * 100) if total > 0 else 0
                expected_ratio = client_ratios[point_client]
                
                if expected_ratio > 0 and current_ratio < expected_ratio:
                    shortage = expected_ratio - current_ratio
                    bonus_multiplier = min(1.0, shortage / 10)
                    score += int(bonus_client * bonus_multiplier)
        
        return score

    def get_statistics(self):
        stats = {}
        if self.constant_df is not None:
            stats['constant_count'] = len(self.constant_df)
            stats['constant_clients'] = self.constant_df['Сеть'].nunique() if 'Сеть' in self.constant_df.columns else 0
            stats['constant_cities'] = self.constant_df['Город'].nunique() if 'Город' in self.constant_df.columns else 0
        if self.variable_df is not None:
            stats['variable_count'] = len(self.variable_df)
            stats['variable_cities'] = self.variable_df['Город'].nunique() if 'Город' in self.variable_df.columns else 0
        if self.retro_df is not None:
            stats['retro_count'] = len(self.retro_df)
            stats['retro_auditors'] = self.retro_df['логин'].nunique() if 'логин' in self.retro_df.columns else 0
        return stats
    
    def check_point_in_polygons(self, lon, lat, polygons):
        if not polygons:
            return False
        point = Point(lon, lat)
        return any(polygon.contains(point) for polygon in polygons)
    
    def _prepare_polygons(self, fact_polygons):
        """
        Подготовка полигонов с кешированием + R-Tree
        """
        if self._polygon_cache is not None:
            return self._polygon_cache
        
        polygon_geoms = []
        polygon_auditors = []
        polygon_cities = []
        polygon_ids = []
        prepared_polygons = []
        
        for poly_id, poly_data in fact_polygons.items():
            coords = poly_data['coordinates']
            if coords and len(coords) >= 3:
                if coords[0] != coords[-1]:
                    coords = coords + [coords[0]]
                poly = Polygon(coords)
                polygon_geoms.append(poly)
                prepared_polygons.append(prep(poly))
                polygon_auditors.append(poly_data['auditor_id'])
                polygon_cities.append(poly_data.get('city', 'Неизвестно'))
                polygon_ids.append(poly_id)
        
        # ========== СОЗДАЁМ R-TREE ==========
        # Только если полигонов > 5 (иначе overhead > выигрыш)
        if len(polygon_geoms) > 5:
            self._rtree = STRtree(polygon_geoms)
            self._polygon_ids_by_geom = {}
            self._polygon_auditors_by_geom = {}
            for i, poly_geom in enumerate(polygon_geoms):
                self._polygon_ids_by_geom[id(poly_geom)] = polygon_ids[i]
                self._polygon_auditors_by_geom[id(poly_geom)] = polygon_auditors[i]
            self._use_rtree = True
        else:
            self._rtree = None
            self._polygon_ids_by_geom = {}
            self._polygon_auditors_by_geom = {}
            self._use_rtree = False
        # ==================================
        
        self._polygon_cache = (prepared_polygons, polygon_ids, polygon_auditors, polygon_cities, polygon_geoms)
        return self._polygon_cache
    
    def _assign_polygons_vectorized(self, df, source_name, polygon_data):
        """
        ВЕКТОРИЗОВАННОЕ присвоение полигонов
        С R-Tree для больших данных
        """
        if df is None or df.empty:
            return pd.DataFrame()
        
        if 'Longitude' not in df.columns or 'Latitude' not in df.columns:
            return pd.DataFrame()
        
        prepared_polygons, polygon_ids, polygon_auditors, polygon_cities, polygon_geoms = polygon_data
        
        if not prepared_polygons:
            return pd.DataFrame()
        
        df_copy = df.copy()
        df_copy['полигон_id'] = None
        df_copy['Аудитор'] = None
        df_copy['Источник'] = source_name
        
        # Создаём точки
        points = []
        valid_indices = []
        for idx, row in df_copy.iterrows():
            try:
                points.append(Point(float(row['Longitude']), float(row['Latitude'])))
                valid_indices.append(idx)
            except (ValueError, TypeError):
                continue
        
        if not points:
            return pd.DataFrame()
        
        # ========== ВЫБОР СТРАТЕГИИ ==========
        if self._use_rtree and self._rtree is not None:
            # БЫСТРЫЙ ПУТЬ: R-Tree (для РФ)
            for point_idx, point in enumerate(points):
                possible = self._rtree.query(point)
                for poly_geom in possible:
                    poly_id = self._polygon_ids_by_geom.get(id(poly_geom))
                    if poly_id is not None and poly_geom.contains(point):
                        df_copy.loc[valid_indices[point_idx], 'полигон_id'] = poly_id
                        df_copy.loc[valid_indices[point_idx], 'Аудитор'] = self._polygon_auditors_by_geom.get(id(poly_geom), '')
                        break
        else:
            # МЕДЛЕННЫЙ ПУТЬ: вложенный цикл (для малых данных)
            for i, (prep_poly, poly_id, auditor) in enumerate(zip(prepared_polygons, polygon_ids, polygon_auditors)):
                mask = np.array([prep_poly.contains(p) for p in points])
                if mask.any():
                    indices_to_assign = []
                    for j, idx in enumerate(valid_indices):
                        if mask[j] and pd.isna(df_copy.loc[idx, 'полигон_id']):
                            indices_to_assign.append(idx)
                    if indices_to_assign:
                        df_copy.loc[indices_to_assign, 'полигон_id'] = poly_id
                        df_copy.loc[indices_to_assign, 'Аудитор'] = auditor
        # ==================================
        
        df_copy = df_copy[df_copy['полигон_id'].notna()]
        return df_copy
    
    def _group_by_polygon(self, points):
        """Группирует точки по полигонам с добавлением _idx"""
        result = {}
        for point in points:
            poly_id = point.get('полигон_id')
            if poly_id:
                if poly_id not in result:
                    result[poly_id] = []
                point['_idx'] = f"{poly_id}_{len(result[poly_id])}_{point.get('Longitude', 0)}_{point.get('Latitude', 0)}"
                result[poly_id].append(point)
        return result
    
    def _get_batch_size(self, num_polygons):
        """Адаптивный выбор размера пакета"""
        if num_polygons <= 3:
            return 3
        elif num_polygons <= 10:
            return 5
        else:
            return 10
    
    def _get_top_proximity_points(self, city, all_candidates_df):
        """
        БЫСТРЫЙ поиск топ-20% ближайших точек к Константе
        """
        if not city or self.constant_df is None or self.constant_df.empty or all_candidates_df.empty:
            return set()
        
        if 'Город' not in all_candidates_df.columns:
            return set()
        if 'Longitude' not in all_candidates_df.columns or 'Latitude' not in all_candidates_df.columns:
            return set()
        
        city_constant = self.constant_df[self.constant_df['Город'] == city]
        if city_constant.empty:
            return set()
        
        if 'Longitude' not in city_constant.columns or 'Latitude' not in city_constant.columns:
            return set()
        
        const_coords = city_constant[['Longitude', 'Latitude']].values
        cand_coords = all_candidates_df[['Longitude', 'Latitude']].values
        
        if len(const_coords) == 0 or len(cand_coords) == 0:
            return set()
        
        min_distances = []
        for cand in cand_coords:
            diff = const_coords - cand
            dist = np.sqrt(np.sum(diff**2, axis=1))
            min_distances.append(np.min(dist))
        
        top_count = max(1, int(len(cand_coords) * 20 / 100))
        if top_count >= len(cand_coords):
            return set(zip(cand_coords[:, 0], cand_coords[:, 1]))
        
        indices = np.argsort(min_distances)[:top_count]
        top_points = cand_coords[indices]
        
        return set(zip(top_points[:, 0], top_points[:, 1]))
    
    def _select_best_point(self, candidates, type_counts, client_counts, total,
                          type_ratios, client_ratios, city_top_points,
                          bonus_type=6, bonus_proximity=5, bonus_client=4):
        """Выбирает лучшую точку с максимальным Score"""
        if not candidates:
            return None, type_counts, client_counts, total
        
        scores = []
        for point in candidates:
            score = self.calculate_score_v2(
                point, type_counts, client_counts, total,
                type_ratios, client_ratios,
                bonus_type, bonus_proximity, bonus_client
            )
            # Бонус за близость
            if (point['Longitude'], point['Latitude']) in city_top_points:
                score += bonus_proximity
            
            scores.append(score)
        
        if not scores:
            return None, type_counts, client_counts, total
        
        best_idx = max(range(len(scores)), key=lambda i: scores[i])
        best_point = candidates[best_idx]
        
        # Обновляем счётчики
        if best_point.get('RED PoS Group'):
            type_name = best_point['RED PoS Group']
            type_counts[type_name] = type_counts.get(type_name, 0) + 1
        if best_point.get('Сеть'):
            client_name = best_point['Сеть']
            client_counts[client_name] = client_counts.get(client_name, 0) + 1
        total += 1
        
        return best_point, type_counts, client_counts, total
    
    def build_plan_balanced(self, fact_polygons, target_ap, 
                            constant_threshold=95, variable_threshold=95, 
                            city_tolerance_percent=0, type_tolerance_percent=0,
                            bonus_type=6, bonus_proximity=5, bonus_client=4):
        """
        ОПТИМИЗИРОВАННАЯ ВЕРСИЯ 2.0
        - R-Tree для быстрой проверки точек
        - Группировка кандидатов через словарь
        - Пакетное добавление точек
        - Адаптивный выбор стратегии
        """
        # Проверки
        if self.constant_df is None:
            return {'status': 'error', 'message': 'Загрузите файл Константы!'}
        
        if not fact_polygons:
            return {'status': 'error', 'message': 'Сначала загрузите факт-полигоны!'}
        
        # 1. Подготовка полигонов (с кешированием + R-Tree)
        polygon_data = self._prepare_polygons(fact_polygons)
        prepared_polygons, polygon_ids, polygon_auditors, polygon_cities, _ = polygon_data
        
        if not prepared_polygons:
            return {'status': 'error', 'message': 'Нет валидных полигонов!'}
        
        # 2. Обработка Константы
        constant_selected_df = self._assign_polygons_vectorized(self.constant_df, 'Константа', polygon_data)
        
        if constant_selected_df.empty:
            return {'status': 'error', 'message': 'Ни одна точка Константы не попала в полигоны!'}
        
        polygon_count = constant_selected_df.groupby('полигон_id').size().to_dict()
        city_count = constant_selected_df.groupby('Город').size().to_dict()
        
        final_ap = constant_selected_df.copy()
        error_points = []
        
        if len(final_ap) >= target_ap:
            final_ap = final_ap.head(target_ap)
            return self._build_result(
                final_ap, constant_selected_df, 
                pd.DataFrame(variable_points) if variable_points else pd.DataFrame(),
                pd.DataFrame(retro_points) if retro_points else pd.DataFrame(),
                error_points, target_ap, len(self.constant_df),
                len(self.variable_df) if self.variable_df is not None else 0,
                len(self.retro_df) if self.retro_df is not None else 0,
                constant_threshold, variable_threshold,
                city_tolerance_percent, type_tolerance_percent,
                city_ratios
            )
        
        # 3. Расчёт целевых показателей
        city_ratios = self.calculate_city_ratios()
        target_by_city = {city: int(target_ap * ratio / 100) for city, ratio in city_ratios.items()}
        
        # 4. Обработка Переменной и Ретро
        variable_selected_df = self._assign_polygons_vectorized(self.variable_df, 'Переменная', polygon_data)
        retro_selected_df = self._assign_polygons_vectorized(self.retro_df, 'Ретро', polygon_data)
        
        # ========== 5. ГРУППИРОВКА КАНДИДАТОВ (СЛОВАРЬ) ==========
        variable_points = variable_selected_df.to_dict('records') if not variable_selected_df.empty else []
        retro_points = retro_selected_df.to_dict('records') if not retro_selected_df.empty else []
        
        variable_by_polygon = self._group_by_polygon(variable_points)
        retro_by_polygon = self._group_by_polygon(retro_points)
        # =========================================================
        
        # ========== 6. АДАПТИВНЫЙ РАЗМЕР ПАКЕТА ==========
        batch_size = self._get_batch_size(len(polygon_ids))
        new_rows = []  # для накопления добавляемых точек
        # =================================================
        
        # 7. Выравнивание полигонов
        cities_sorted = sorted(city_count.keys(), key=lambda c: city_count.get(c, 0))
        
        # ========== ЗАЩИТА ОТ ПУСТЫХ ДАННЫХ ==========
        all_candidates_list = []
        if not variable_selected_df.empty:
            all_candidates_list.append(variable_selected_df)
        if not retro_selected_df.empty:
            all_candidates_list.append(retro_selected_df)
        
        all_candidates_df = pd.concat(all_candidates_list, ignore_index=True) if all_candidates_list else pd.DataFrame()
        # =============================================
        
        for city in cities_sorted:
            if len(final_ap) + len(new_rows) >= target_ap:
                break
            
            city_polygons = [p for p in polygon_ids if polygon_count.get(p, 0) > 0]
            if not city_polygons:
                continue
            
            # ========== ПРОВЕРКА ПЕРЕД ИСПОЛЬЗОВАНИЕМ ==========
            if not all_candidates_df.empty and 'Город' in all_candidates_df.columns:
                city_candidates = all_candidates_df[all_candidates_df['Город'] == city]
            else:
                city_candidates = pd.DataFrame()
            # =================================================
            city_top_points = self._get_top_proximity_points(city, city_candidates)
            
            current_counts = {p: polygon_count.get(p, 0) for p in city_polygons}
            
            # ========== 8. ПОДГОТОВКА ПРОПОРЦИЙ ОДИН РАЗ ==========
            current_ap = pd.concat([final_ap, pd.DataFrame(new_rows)], ignore_index=True) if new_rows else final_ap
            type_counts = current_ap['RED PoS Group'].value_counts() if not current_ap.empty else pd.Series()
            client_counts = current_ap['Сеть'].value_counts() if not current_ap.empty else pd.Series()
            total = len(current_ap)
            # =====================================================
            
            max_iterations = 100
            for _ in range(max_iterations):
                if len(final_ap) + len(new_rows) >= target_ap:
                    break
                
                min_count = min(current_counts.values())
                max_count = max(current_counts.values())
                
                if max_count - min_count <= 1:
                    break
                
                sorted_polygons = sorted(city_polygons, key=lambda p: current_counts.get(p, 0))
                
                for poly_id in sorted_polygons:
                    if len(final_ap) + len(new_rows) >= target_ap:
                        break
                    
                    if target_by_city.get(city, 0) > 0 and city_count.get(city, 0) >= target_by_city[city]:
                        break
                    
                    # ========== 9. КАНДИДАТЫ ИЗ СЛОВАРЯ ==========
                    candidates = []
                    if poly_id in variable_by_polygon:
                        candidates.extend(variable_by_polygon[poly_id])
                    if poly_id in retro_by_polygon:
                        candidates.extend(retro_by_polygon[poly_id])
                    # =============================================
                    
                    if not candidates:
                        continue
                    
                    # ========== 10. ВЫБОР ЛУЧШЕЙ ТОЧКИ ==========
                    best_point, type_counts, client_counts, total = self._select_best_point(
                        candidates, type_counts, client_counts, total,
                        self.type_ratios, self.client_ratios, city_top_points,
                        bonus_type, bonus_proximity, bonus_client
                    )
                    # =============================================
                    
                    if best_point is None:
                        continue
                    
                    # Определяем источник
                    is_variable = False
                    if poly_id in variable_by_polygon:
                        for p in variable_by_polygon[poly_id]:
                            if p.get('_idx') == best_point.get('_idx'):
                                is_variable = True
                                break
                    
                    # Удаляем из источников
                    if poly_id in variable_by_polygon:
                        variable_by_polygon[poly_id] = [
                            p for p in variable_by_polygon[poly_id] 
                            if p.get('_idx') != best_point.get('_idx')
                        ]
                    if poly_id in retro_by_polygon:
                        retro_by_polygon[poly_id] = [
                            p for p in retro_by_polygon[poly_id] 
                            if p.get('_idx') != best_point.get('_idx')
                        ]
                    
                    best_point['Источник'] = 'Переменная' if is_variable else 'Ретро'
                    
                    # ========== 11. НАКОПЛЕНИЕ В new_rows ==========
                    new_rows.append(best_point)
                    current_counts[poly_id] = current_counts.get(poly_id, 0) + 1
                    city_count[city] = city_count.get(city, 0) + 1
                    # =================================================
                    
                    if len(final_ap) + len(new_rows) >= target_ap:
                        break
        
        # ========== 12. ОДИН concat В КОНЦЕ ==========
        if new_rows:
            valid_rows = [row for row in new_rows if row and isinstance(row, dict)]
            if valid_rows:
                final_ap = pd.concat([final_ap, pd.DataFrame(valid_rows)], ignore_index=True)
        # =============================================

        # 13. Финальная статистика
        return self._build_result(
            final_ap, constant_selected_df, 
            pd.DataFrame(variable_points) if variable_points else pd.DataFrame(),
            pd.DataFrame(retro_points) if retro_points else pd.DataFrame(),
            error_points, target_ap, len(self.constant_df),
            len(self.variable_df) if self.variable_df is not None else 0,
            len(self.retro_df) if self.retro_df is not None else 0,
            constant_threshold, variable_threshold,
            city_tolerance_percent, type_tolerance_percent,
            city_ratios
        )
    
    def _build_result(self, final_ap, constant_selected, variable_selected, retro_selected,
                      error_points, target_ap, constant_total, variable_total, retro_total,
                      constant_threshold, variable_threshold,
                      city_tolerance_percent=0, type_tolerance_percent=0,
                      city_ratios=None):
        """Формирует результат (статистика, утилизация, предупреждения)"""
        final_count = len(final_ap)
        plan_completion = (final_count / target_ap * 100) if target_ap > 0 else 0
        
        if not final_ap.empty and 'Источник' in final_ap.columns:
            constant_fact = len(final_ap[final_ap['Источник'] == 'Константа'])
            variable_fact = len(final_ap[final_ap['Источник'] == 'Переменная'])
            retro_fact = len(final_ap[final_ap['Источник'] == 'Ретро'])
        else:
            constant_fact = variable_fact = retro_fact = 0
        
        constant_utilization = (constant_fact / constant_total * 100) if constant_total > 0 else 0
        variable_utilization = (variable_fact / variable_total * 100) if variable_total > 0 else 0
        retro_utilization = (retro_fact / retro_total * 100) if retro_total > 0 else 0
        
        # Проверка пропорций по городам
        city_warnings = []
        if city_ratios and not final_ap.empty:
            actual_city_counts = final_ap['Город'].value_counts()
            total = len(final_ap)
            
            all_cities = set(actual_city_counts.index) | set(city_ratios.keys())
            
            for city in all_cities:
                actual_count = actual_city_counts.get(city, 0)
                actual_ratio = (actual_count / total * 100) if total > 0 else 0
                expected_ratio = city_ratios.get(city, 0)
                
                if expected_ratio > 0:
                    deviation_percent = abs(actual_ratio - expected_ratio) / expected_ratio * 100
                else:
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
