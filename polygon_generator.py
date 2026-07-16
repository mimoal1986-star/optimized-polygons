import numpy as np
from shapely.geometry import Point, Polygon, MultiPoint
import json
import os
from datetime import datetime

class PolygonGenerator:
    def __init__(self, data_processor):
        self.data_processor = data_processor
    
    def create_polygon_for_auditor(self, auditor_id, buffer_km=0.5):
        records = self.data_processor.get_data_by_auditor(auditor_id)
        
        if len(records) < 3:
            return None, f"Недостаточно точек для создания полигона (нужно минимум 3, есть {len(records)})"
        
        points = []
        for record in records:
            if 'lat' in record and 'lon' in record:
                try:
                    lat = float(record['lat'])
                    lon = float(record['lon'])
                    points.append((lon, lat))
                except (ValueError, TypeError):
                    continue
        
        if len(points) < 3:
            return None, f"Недостаточно валидных точек с координатами (нужно минимум 3, есть {len(points)})"
        
        try:
            multi_point = MultiPoint(points)
            hull = multi_point.convex_hull
            
            if hull.geom_type != 'Polygon':
                return None, "Точки образуют линию, полигон не может быть создан"
            
            buffer_deg = buffer_km / 111.0
            expanded_polygon = hull.buffer(buffer_deg, resolution=4)
            
            if expanded_polygon.geom_type == 'MultiPolygon':
                expanded_polygon = max(expanded_polygon.geoms, key=lambda p: p.area)
            
            coords = list(expanded_polygon.exterior.coords)
            area_km2 = expanded_polygon.area * 111 * 111
            
            return {
                'auditor_id': auditor_id,
                'points_count': len(points),
                'coordinates': [(float(lon), float(lat)) for lon, lat in coords],
                'area_km2': area_km2,
                'center': [float(coords[0][0]), float(coords[0][1])]
            }, None
            
        except Exception as e:
            return None, f"Ошибка при создании полигона: {str(e)}"
    
    
    def create_polygons_for_all_auditors(self, min_points=3, buffer_km=0.5):
        auditors = self.data_processor.get_auditors()
        polygons = []
        errors = []
        
        if not auditors:
            return polygons, ["Нет аудиторов в данных"]
        
        for auditor in auditors:
            polygon, error = self.create_polygon_for_auditor(auditor, buffer_km)
            if polygon:
                polygons.append(polygon)
            else:
                errors.append(f"{auditor}: {error if error else 'Неизвестная ошибка'}")
        
        return polygons, errors
    
    def export_to_geojson(self, polygons_data, filename='data/polygons.geojson'):
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
                    'area_km2': float(polygon_data.get('area_km2', 0))
                }
            }
            features.append(feature)
        
        geojson = {
            'type': 'FeatureCollection',
            'features': features
        }
        
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(geojson, f, ensure_ascii=False, indent=2)
        
        return filename
