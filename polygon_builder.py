from shapely.geometry import MultiPoint
from cluster_engine import ClusterEngine

class PolygonBuilder:
    
    def __init__(self, data_processor):
        self.data_processor = data_processor
    
    def build_polygon(self, cluster, auditor_id, city, cluster_id, buffer_km=0.5):
        """
        Строит полигон из кластера с использованием Convex Hull + Buffer + Упрощение
        """
        if len(cluster) < 3:
            return None
        
        try:
            # 1. Convex Hull
            multi_point = MultiPoint(cluster)
            hull = multi_point.convex_hull
            
            # Проверка на полигон
            if hull.geom_type != 'Polygon':
                # Если точки на линии → расширяем
                buffer_deg = buffer_km / 111.0
                hull = hull.buffer(buffer_deg)
                if hull.geom_type == 'MultiPolygon':
                    hull = max(hull.geoms, key=lambda p: p.area)
            
            # 2. Буфер (расширение)
            buffer_deg = buffer_km / 111.0
            expanded = hull.buffer(buffer_deg, resolution=4)
            
            # Если получился MultiPolygon → берем самый большой
            if expanded.geom_type == 'MultiPolygon':
                expanded = max(expanded.geoms, key=lambda p: p.area)
            
            # 3. Упрощение полигона (уменьшаем количество вершин)
            # 0.005 градуса ≈ 550 метров — оптимально для Google My Maps
            SIMPLIFY_TOLERANCE = 0.002
            simplified = expanded.simplify(SIMPLIFY_TOLERANCE, preserve_topology=True)
            
            # Если упрощение дало меньше 4 точек — используем оригинал
            if len(simplified.exterior.coords) < 4:
                simplified = expanded
            
            coords = list(simplified.exterior.coords)
            
            # 4. Площадь в км²
            area_km2 = simplified.area * 111 * 111
            
            # 5. Центр полигона
            center_lon = sum([c[0] for c in coords]) / len(coords)
            center_lat = sum([c[1] for c in coords]) / len(coords)
            
            return {
                'auditor_id': auditor_id,
                'city': city,
                'cluster_id': cluster_id,
                'points_count': len(cluster),
                'coordinates': coords,  # [(lon, lat), ...]
                'area_km2': area_km2,
                'center': [center_lon, center_lat]
            }
            
        except Exception as e:
            print(f"Ошибка построения полигона: {e}")
            return None
    
    def build_polygons_for_auditor(self, auditor_id, buffer_km=0.5, min_points=3):
        """
        Строит все полигоны для одного аудитора
        Возвращает список полигонов
        """
        # Получаем точки по городам
        cities_points = self.data_processor.get_points_by_city(auditor_id)
        
        all_polygons = []
        
        for city, points in cities_points.items():
            # Проверяем, что город в списке миллионников
            if not ClusterEngine.is_million_city(city):
                continue
            
            if len(points) < min_points:
                continue
            
            # Кластеризация
            clusters = ClusterEngine.cluster_points(points, min_samples=min_points)
            
            for i, cluster in enumerate(clusters):
                if len(cluster) < min_points:
                    continue
                
                polygon = self.build_polygon(
                    cluster, 
                    auditor_id, 
                    city, 
                    i + 1, 
                    buffer_km
                )
                if polygon:
                    all_polygons.append(polygon)
        
        return all_polygons
