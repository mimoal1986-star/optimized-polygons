import numpy as np
from shapely.geometry import Point, Polygon, MultiPoint
import simplekml
import json
import os
from datetime import datetime
import traceback

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
            hull = multi_point.convex_hull  # ← ЗДЕСЬ
            
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
    
    def generate_kml(self, polygons_data, city_name=None):
        """Генерация KML файла с полигонами и точками"""
        try:
            print(f"📝 Начинаем создание KML. Полигонов: {len(polygons_data)}")
            
            kml = simplekml.Kml()
            print("✅ KML объект создан")
            
            polystyle = simplekml.Style()
            polystyle.polystyle.color = simplekml.Color.hex('7f00ff00')
            polystyle.polystyle.outline = 1
            polystyle.linestyle.color = simplekml.Color.hex('ff00ff00')
            polystyle.linestyle.width = 2
            
            kml.document.style = polystyle
            print("✅ Стиль применен")
            
            for i, polygon_data in enumerate(polygons_data):
                print(f"  📍 Обработка полигона {i+1}/{len(polygons_data)}: {polygon_data.get('auditor_id', 'unknown')}")
                
                if 'coordinates' not in polygon_data or not polygon_data['coordinates']:
                    print(f"  ⚠️ Пропускаем: нет координат")
                    continue
                
                try:
                    placemark = kml.newpolygon(name=f"🗺️ {polygon_data['auditor_id']}")
                    
                    description = f"Аудитор: {polygon_data['auditor_id']}\n"
                    description += f"Количество точек: {polygon_data.get('points_count', 0)}\n"
                    if 'area_km2' in polygon_data:
                        description += f"Площадь: {polygon_data['area_km2']:.1f} км²"
                    
                    placemark.description = description
                    
                    coords = polygon_data['coordinates'].copy()
                    if coords and coords[0] != coords[-1]:
                        coords.append(coords[0])
                    
                    placemark.polygon.outerboundaryis = [
                        (float(lon), float(lat), 0) for lon, lat in coords
                    ]
                    print(f"  ✅ Полигон {polygon_data['auditor_id']} добавлен (точек: {len(coords)})")
                    
                    auditor_records = self.data_processor.get_data_by_auditor(
                        polygon_data['auditor_id']
                    )
                    print(f"  📍 Добавляем {len(auditor_records)} точек для {polygon_data['auditor_id']}")
                    
                    for record in auditor_records:
                        if 'lat' in record and 'lon' in record:
                            try:
                                lat = float(record['lat'])
                                lon = float(record['lon'])
                                point_placemark = kml.newpoint(
                                    name=f"Точка {record.get('tp_id', '')}"
                                )
                                point_placemark.coords = [(lon, lat)]
                                point_placemark.style.iconstyle.color = simplekml.Color.red
                                point_placemark.style.iconstyle.scale = 0.5
                            except (ValueError, TypeError):
                                continue
                    
                except Exception as e:
                    print(f"  ❌ Ошибка при добавлении полигона {polygon_data.get('auditor_id', 'unknown')}: {str(e)}")
                    continue
            
            filename = f"polygons_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            if city_name:
                filename = f"{city_name}_{filename}"
            
            print(f"📁 Создаем папку data...")
            os.makedirs('data', exist_ok=True)
            
            kml_file = f"data/{filename}.kml"
            print(f"💾 Сохраняем KML: {kml_file}")
            kml.save(kml_file)
            print(f"✅ KML сохранен")
            
            if os.path.exists(kml_file):
                file_size = os.path.getsize(kml_file)
                print(f"📊 Размер файла: {file_size} байт")
                return kml_file
            else:
                print(f"❌ Файл не создался!")
                return None
            
        except Exception as e:
            print(f"❌ ОШИБКА при создании KML: {str(e)}")
            print(traceback.format_exc())
            return None
    
    def create_polygons_for_all_auditors(self, min_points=3, buffer_km=0.5):
        auditors = self.data_processor.get_auditors()
        polygons = []
        errors = []
        
        if not auditors:
            return polygons, ["Нет аудиторов в данных"]
        
        print(f"📊 Найдено аудиторов: {len(auditors)}")
        
        for auditor in auditors:
            print(f"  🔄 Обработка аудитора: {auditor}")
            polygon, error = self.create_polygon_for_auditor(auditor, buffer_km)
            if polygon:
                polygons.append(polygon)
                print(f"  ✅ Полигон создан: {auditor} (точек: {polygon['points_count']})")
            else:
                errors.append(f"{auditor}: {error if error else 'Неизвестная ошибка'}")
                print(f"  ❌ Ошибка: {error}")
        
        print(f"📊 Итог: создано {len(polygons)} полигонов, ошибок: {len(errors)}")
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
