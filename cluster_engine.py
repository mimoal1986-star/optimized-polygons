import numpy as np
from sklearn.cluster import DBSCAN
from sklearn.neighbors import NearestNeighbors

class ClusterEngine:
    
    # Список городов-миллионников
    MILLION_CITIES = [
        'Волгоград', 'Воронеж', 'Екатеринбург', 'Казань',
        'Краснодар', 'Красноярск', 'Москва', 'Нижний Новгород',
        'Новосибирск', 'Омск', 'Пермь', 'Ростов-на-Дону',
        'Самара', 'Санкт-Петербург', 'Уфа', 'Челябинск'
    ]
    
    @staticmethod
    def auto_eps(points):
        """
        Автоматический подбор eps методом 'колена'
        """
        if len(points) < 5:
            return 0.01
        
        coords = np.array(points)
        
        # Расстояния до ближайших соседей
        n_neighbors = min(5, len(points) - 1)
        if n_neighbors < 2:
            return 0.01
            
        nbrs = NearestNeighbors(n_neighbors=n_neighbors)
        nbrs.fit(coords)
        distances, _ = nbrs.kneighbors(coords)
        
        # Берем расстояние до последнего соседа
        k_distances = np.sort(distances[:, -1])
        
        # Ищем "колено" (точку максимального изгиба)
        if len(k_distances) > 2:
            diffs = np.diff(k_distances)
            if len(diffs) > 0:
                knee_idx = np.argmax(diffs)
                eps = k_distances[min(knee_idx + 1, len(k_distances) - 1)]
            else:
                eps = k_distances[-1] * 0.5
        else:
            eps = 0.01
        
        # Ограничиваем
        eps = max(eps, 0.0005)   # минимум 50 метров
        eps = min(eps, 0.05)     # максимум 5 км
        
        return eps
    
    @staticmethod
    def cluster_points(points, eps=None, min_samples=3):
        """
        Кластеризация точек DBSCAN
        Возвращает список кластеров: [[(lon, lat), ...], ...]
        """
        if len(points) < 3:
            return [points]
        
        coords = np.array(points)
        
        if eps is None:
            eps = ClusterEngine.auto_eps(points)
        
        # DBSCAN кластеризация
        clustering = DBSCAN(eps=eps, min_samples=min_samples).fit(coords)
        labels = clustering.labels_
        
        # Собираем кластеры
        clusters = {}
        for i, label in enumerate(labels):
            if label == -1:
                continue  # выбросы пропускаем
            if label not in clusters:
                clusters[label] = []
            clusters[label].append(points[i])
        
        # Если кластеров нет → все точки в один кластер
        if not clusters:
            return [points]
        
        # Сортируем по размеру
        result = sorted(clusters.values(), key=len, reverse=True)
        
        # Фильтруем по минимальному размеру
        result = [c for c in result if len(c) >= min_samples]
        
        return result if result else [points]
    
    @staticmethod
    def is_million_city(city):
        """Проверяет, входит ли город в список миллионников"""
        return city in ClusterEngine.MILLION_CITIES