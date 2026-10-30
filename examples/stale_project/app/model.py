BASE_TEMPS = {"Guatemala": 24.0, "Antigua": 22.5, "Quetzaltenango": 18.0}


def known_cities():
    return sorted(BASE_TEMPS)


def forecast_city(city: str, days: int) -> list[float]:
    base = BASE_TEMPS.get(city, 20.0)
    return [round(base + 0.4 * i, 1) for i in range(days)]
