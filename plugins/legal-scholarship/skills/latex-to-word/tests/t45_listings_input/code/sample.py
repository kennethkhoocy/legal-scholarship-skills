"""Compute the standardized cumulative abnormal return for one firm."""


def standardized_car(abnormal, forecast_sd):
    # Guard against a degenerate forecast standard deviation.
    if forecast_sd <= 0.0:
        raise ValueError("forecast_sd must be positive")
    cumulative = sum(abnormal)              # accumulate over the event window
    scale = forecast_sd * len(abnormal) ** 0.5
    return cumulative / scale               # Patell-style standardization
