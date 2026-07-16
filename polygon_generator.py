import numpy as np
from shapely.geometry import Point, Polygon, MultiPoint
from shapely.validation import make_valid
from shapely.ops import transform
import simplekml
import json
import os
from datetime import datetime
import traceback
import logging
from typing import Dict, List, Tuple, Optional
from functools import partial

# Попытка импорта alphashape
try:
    import alphashape
    ALPHASHAPE_AVAILABLE = True
except ImportError:
    ALPHASHAPE_AVAILABLE = False
    print("⚠️ alphashape не установлен, используем Convex Hull")

# Попытка импорта pyproj
try:
    import pyproj
    PYPROJ_AVAILABLE = True
except ImportError:
    PYPROJ_AVAILABLE = False
    print("⚠️ pyproj не установлен, площадь будет рассчитана приблизительно")

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PolygonGenerator:
    def __init__(self, data_processor):
        self.data_processor = data_processor
        self.backup_dir = 'data'
        os.makedirs(self.backup_dir, exist_ok=True)
    
    def create_polygon_for_auditor(
        self, 
        auditor_id: str, 
        buffer_km: float = 0.5,
        min_points: int = 3
    ) -> Tuple[Optional[Dict], Optional[str]]:
        """Создание полигона для аудитора"""
        try:
            records = self.data_processor.get_data_by_auditor(auditor_id)
            
            if len(records) < min_points:
                return None, f"Недостаточно точек: {len(records)} (нужно {min_points})"
            
            points = []
            for record in records:
                if 'lat' in record and 'lon' in record:
                    try:
                        lat = float(record['lat'])
                        lon = float(record['lon'])
                        
                        if self._validate_coordinates(lat, lon):
                            points.append((lon, lat))
                    except (ValueError, TypeError):
                        continue
            
            if len(points) < min_points:
                return None, f"Недостаточно валидных точек: {len(points)} (нужно {min_points})"
            
            points = self._deduplicate_points(points)
            
            if len(points) < min_points:
                return None, f"После дедупликации осталось {len(points)} точек (нужно {min_points})"
            
            polygon = self._create_alpha_polygon(points, buffer_km)
            
            if polygon is None:
                return None, "Не удалось создать полигон"
            
            if not polygon.is_valid:
                logger.warning(f"Полигон невалиден для {auditor_id}, исправляем...")
                polygon = make_valid(polygon)
                
                if polygon.geom_type == 'MultiPolygon':
                    polygon = max(polygon.geoms, key=lambda p: p.area)
                elif polygon.geom_type != 'Polygon':
                    return None, f"Полигон имеет тип {polygon.geom_type}, ожидается Polygon"
            
            area_km2 = self._calculate_area_km2(polygon)
            
            coords = list(polygon.exterior.coords)
            
            return {
                'auditor_id': auditor_id,
                'points_count': len(points),
                'coordinates': [(float(lon), float(lat)) for lon, lat in coords],
                'area_km2': area_km2,
                'center': [float(coords[0][0]), float(coords[0][1])]
            }, None
            
        except Exception as e:
            logger.error(f"Ошибка создания полигона для {auditor_id}: {str(e)}", exc_info=True)
            return None, f"Ошибка: {str(e)}"
    
    def _validate_coordinates(self, lat: float, lon: float) -> bool:
        """Валидация координат"""
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            return False
        if not (-90 <= lat <= 90):
            return False
        if not (-180 <= lon <= 180):
            return False
        return True
    
    def _deduplicate_points(self, points: List[tuple], tolerance: float = 0.0001) -> List[tuple]:
        """Дедупликация точек"""
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
        
        if len(points) != len(unique):
            logger.info(f"Дедупликация: {len(points)} -> {len(unique)} точек")
        
        return unique
    
    def _create_alpha_polygon(self, points: List[tuple], buffer_km: float) -> Optional[Polygon]:
        """Создание полигона с использованием Alpha Shape"""
        try:
            if len(points) < 4:
                multi_point = MultiPoint(points)
                hull = multi_point.convex_hull
            else:
                if ALPHASHAPE_AVAILABLE:
                    try:
                        alpha = 0.5
                        hull = alphashape.alphashape(points, alpha)
                        
                        if hull.geom_type != 'Polygon':
                            logger.warning(f"Alpha Shape вернул {hull.geom_type}, используем Convex Hull")
                            multi_point = MultiPoint(points)
                            hull = multi_point.convex_hull
                    except Exception as e:
                        logger.warning(f"Alpha Shape не удался: {e}, используем Convex Hull")
                        multi_point = MultiPoint(points)
                        hull = multi_point.convex_hull
                else:
                    multi_point = MultiPoint(points)
                    hull = multi_point.convex_hull
            
            if hull.geom_type != 'Polygon':
                return None
            
            # Буфер в градусах
            avg_lat = np.mean([p[1] for p in points])
            km_per_degree = 111.32 * np.cos(np.radians(avg_lat))
            buffer_deg = buffer_km / km_per_degree
            
            expanded_polygon = hull.buffer(buffer_deg, resolution=8)
            
            if expanded_polygon.geom_type == 'MultiPolygon':
                expanded_polygon = max(expanded_polygon.geoms, key=lambda p: p.area)
            
            return expanded_polygon
            
        except Exception as e:
            logger.error(f"Ошибка создания полигона: {e}")
            return None
    
    def _calculate_area_km2(self, polygon: Polygon) -> float:
        """Расчет площади в км² с использованием проекции"""
        try:
            if PYPROJ_AVAILABLE:
                centroid = polygon.centroid
                utm_zone = int((centroid.x + 180) / 6) + 1
                epsg_code = 32600 + utm_zone if centroid.y >= 0 else 32700 + utm_zone
                
                project = partial(
                    pyproj.transform,
                    pyproj.Proj('EPSG:4326'),
                    pyproj.Proj(f'EPSG:{epsg_code}')
                )
                
                projected_polygon = transform(project, polygon)
                area_m2 = projected_polygon.area
                area_km2 = area_m2 / 1_000_000
                
                return area_km2
            else:
                # Fallback: грубая оценка
                return polygon.area * 111 * 111
            
        except Exception as e:
            logger.error(f"Ошибка расчета площади: {e}")
            return polygon.area * 111 * 111
    
    def generate_kml(self, polygons_data: List[Dict], city_name: Optional[str] = None) -> Optional[str]:
        """Генерация KML файла"""
        try:
            logger.info(f"Начинаем создание KML. Полигонов: {len(polygons_data)}")
            
            kml = simplekml.Kml()
            
            polystyle = simplekml.Style()
            polystyle.id = 'polygonStyle'
            polystyle.polystyle.color = '7f00ff00'
            polystyle.polystyle.outline = 1
            polystyle.linestyle.color = 'ff00ff00'
            polystyle.linestyle.width = 2
            
            kml.document.add_style(polystyle)
            
            pointstyle = simplekml.Style()
            pointstyle.id = 'pointStyle'
            pointstyle.iconstyle.color = simplekml.Color.red
            pointstyle.iconstyle.scale = 0.7
            
            kml.document.add_style(pointstyle)
            
            created_count = 0
            
            for i, polygon_data in enumerate(polygons_data):
                if 'coordinates' not in polygon_data or not polygon_data['coordinates']:
                    continue
                
                try:
                    auditor_id = polygon_data['auditor_id']
                    
                    auditor_records = self.data_processor.get_data_by_auditor(auditor_id)
                    city_from_data = city_name if city_name else 'Город'
                    
                    if auditor_records and len(auditor_records) > 0:
                        city_from_data = auditor_records[0].get('city', city_from_data)
                    
                    placemark_name = f"🗺️ {city_from_data} - {auditor_id}"
                    
                    description = f"""
                    <b>Аудитор:</b> {auditor_id}<br>
                    <b>Город:</b> {city_from_data}<br>
                    <b>Точек:</b> {polygon_data.get('points_count', 0)}<br>
                    <b>Площадь:</b> {polygon_data.get('area_km2', 0):.2f} км²<br>
                    <b>Дата:</b> {datetime.now().strftime('%d.%m.%Y')}
                    """
                    
                    placemark = kml.newpolygon(name=placemark_name)
                    placemark.description = description
                    placemark.styleUrl = '#polygonStyle'
                    
                    coords = polygon_data['coordinates'].copy()
                    if coords and coords[0] != coords[-1]:
                        coords.append(coords[0])
                    
                    placemark.polygon.outerboundaryis = [
                        (float(lon), float(lat), 0) for lon, lat in coords
                    ]
                    
                    for record in auditor_records[:100]:
                        if 'lat' in record and 'lon' in record:
                            try:
                                lat = float(record['lat'])
                                lon = float(record['lon'])
                                
                                if self._validate_coordinates(lat, lon):
                                    point_placemark = kml.newpoint(
                                        name=f"📍 {record.get('tp_id', '')}"
                                    )
                                    point_placemark.coords = [(lon, lat)]
                                    point_placemark.styleUrl = '#pointStyle'
                                    point_placemark.description = f"""
                                    <b>ТП:</b> {record.get('tp_id', '')}<br>
                                    <b>Дата:</b> {record.get('visit_date', '')}<br>
                                    <b>Адрес:</b> {record.get('address', '')}
                                    """
                            except (ValueError, TypeError):
                                continue
                    
                    created_count += 1
                    
                except Exception as e:
                    logger.error(f"Ошибка создания полигона {i}: {e}")
                    continue
            
            if created_count == 0:
                logger.error("Не создано ни одного полигона")
                return None
            
            filename = f"polygons_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            if city_name:
                filename = f"{city_name}_{filename}"
            
            kml_file = os.path.join(self.backup_dir, f"{filename}.kml")
            kml.save(kml_file)
            
            if os.path.exists(kml_file):
                logger.info(f"KML файл создан: {kml_file}, полигонов: {created_count}")
                return kml_file
            else:
                return None
            
        except Exception as e:
            logger.error(f"Ошибка создания KML: {str(e)}", exc_info=True)
            return None
    
    def create_polygons_for_all_auditors(
        self, 
        min_points: int = 3, 
        buffer_km: float = 0.5
    ) -> Tuple[List[Dict], List[str]]:
        """Создание полигонов для всех аудиторов"""
        auditors = self.data_processor.get_auditors()
        polygons = []
        errors = []
        
        if not auditors:
            return polygons, ["Нет аудиторов в данных"]
        
        logger.info(f"Начинаем генерацию для {len(auditors)} аудиторов")
        
        for auditor in auditors:
            polygon, error = self.create_polygon_for_auditor(
                auditor, 
                buffer_km=buffer_km,
                min_points=min_points
            )
            
            if polygon:
                polygons.append(polygon)
                logger.info(f"Полигон создан для {auditor}: {polygon['points_count']} точек")
            else:
                errors.append(f"{auditor}: {error if error else 'Неизвестная ошибка'}")
                logger.warning(f"Не удалось создать полигон для {auditor}: {error}")
        
        logger.info(f"Генерация завершена. Создано: {len(polygons)}, ошибок: {len(errors)}")
        return polygons, errors
    
    def export_to_geojson(self, polygons_data: List[Dict], filename: str = None) -> str:
        """Экспорт в GeoJSON"""
        if filename is None:
            filename = os.path.join(self.backup_dir, f"polygons_{datetime.now().strftime('%Y%m%d_%H%M%S')}.geojson")
        
        features = []
        
        for polygon_data in polygons_data:
            if 'coordinates' not in polygon_data or not polygon_data['coordinates']:
                continue
            
            coords = polygon_data['coordinates'].copy()
            if coords and coords[0] != coords[-1]:
                coords.append(coords[0])
            
            feature = {
                'type': 'Feature',
                'geometry': {
                    'type': 'Polygon',
                    'coordinates': [coords]
                },
                'properties': {
                    'auditor_id': polygon_data['auditor_id'],
                    'points_count': polygon_data.get('points_count', 0),
                    'area_km2': float(polygon_data.get('area_km2', 0)),
                    'created_at': datetime.now().isoformat()
                }
            }
            features.append(feature)
        
        geojson = {
            'type': 'FeatureCollection',
            'features': features
        }
        
        os.makedirs(os.path.dirname(filename) or '.', exist_ok=True)
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(geojson, f, ensure_ascii=False, indent=2)
        
        logger.info(f"GeoJSON создан: {filename}, полигонов: {len(features)}")
        return filename
