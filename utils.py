def normalize_answer(value):
    return str(value or "").strip().lower()


def sanitize_int(value, default_value, minimum=1, maximum=10_000):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default_value
    return max(minimum, min(maximum, parsed))


def sanitize_ratio(value, default_value):
    return sanitize_int(value, default_value, 0, 100)
