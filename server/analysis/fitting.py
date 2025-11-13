"""Curve fitting and regression analysis module."""

import numpy as np
import logging
from typing import Callable, Optional
from scipy import optimize

from .models import FitConfig, FitResult, FitType

logger = logging.getLogger(__name__)


class CurveFitter:
    """Curve fitting and regression engine."""

    def __init__(self):
        """Initialize curve fitter."""
        pass

    def fit(
        self, x_data: np.ndarray, y_data: np.ndarray, config: FitConfig
    ) -> FitResult:
        """Fit curve to data.

        Args:
            x_data: X values
            y_data: Y values
            config: Fit configuration

        Returns:
            FitResult with fit parameters and statistics
        """
        fit_type = config.fit_type

        # Perform fit based on type
        if fit_type == FitType.LINEAR:
            coeffs, fitted_y, equation = self._fit_linear(x_data, y_data)

        elif fit_type == FitType.POLYNOMIAL:
            coeffs, fitted_y, equation = self._fit_polynomial(
                x_data, y_data, config.degree, config.weights
            )

        elif fit_type == FitType.EXPONENTIAL:
            coeffs, fitted_y, equation = self._fit_exponential(
                x_data, y_data, config.initial_guess, config.bounds
            )

        elif fit_type == FitType.LOGARITHMIC:
            coeffs, fitted_y, equation = self._fit_logarithmic(
                x_data, y_data, config.initial_guess
            )

        elif fit_type == FitType.POWER:
            coeffs, fitted_y, equation = self._fit_power(
                x_data, y_data, config.initial_guess
            )

        elif fit_type == FitType.SINUSOIDAL:
            coeffs, fitted_y, equation = self._fit_sinusoidal(
                x_data, y_data, config.initial_guess
            )

        elif fit_type == FitType.GAUSSIAN:
            coeffs, fitted_y, equation = self._fit_gaussian(
                x_data, y_data, config.initial_guess
            )

        elif fit_type == FitType.CUSTOM:
            if not config.custom_function:
                raise ValueError("Custom fit requires custom_function")
            coeffs, fitted_y, equation = self._fit_custom(
                x_data, y_data, config.custom_function, config.initial_guess, config.bounds
            )

        else:
            raise ValueError(f"Unknown fit type: {fit_type}")

        # Calculate statistics
        residuals = y_data - fitted_y
        r_squared = self._calculate_r_squared(y_data, fitted_y)
        rmse = np.sqrt(np.mean(residuals**2))

        return FitResult(
            coefficients=coeffs.tolist(),
            fitted_data=fitted_y.tolist(),
            x_data=x_data.tolist(),
            y_data=y_data.tolist(),
            r_squared=float(r_squared),
            rmse=float(rmse),
            residuals=residuals.tolist(),
            equation=equation,
            config=config,
        )

    def _fit_linear(
        self, x_data: np.ndarray, y_data: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray, str]:
        """Fit linear model: y = mx + b."""
        coeffs = np.polyfit(x_data, y_data, 1)
        fitted_y = np.polyval(coeffs, x_data)
        equation = f"y = {coeffs[0]:.6g}x + {coeffs[1]:.6g}"
        return coeffs, fitted_y, equation

    def _fit_polynomial(
        self, x_data: np.ndarray, y_data: np.ndarray, degree: int, weights: Optional[np.ndarray]
    ) -> tuple[np.ndarray, np.ndarray, str]:
        """Fit polynomial model."""
        coeffs = np.polyfit(x_data, y_data, degree, w=weights)
        fitted_y = np.polyval(coeffs, x_data)

        # Build equation string
        terms = []
        for i, coeff in enumerate(coeffs):
            power = degree - i
            if power == 0:
                terms.append(f"{coeff:.6g}")
            elif power == 1:
                terms.append(f"{coeff:.6g}x")
            else:
                terms.append(f"{coeff:.6g}x^{power}")

        equation = "y = " + " + ".join(terms)
        return coeffs, fitted_y, equation

    def _fit_exponential(
        self,
        x_data: np.ndarray,
        y_data: np.ndarray,
        initial_guess: Optional[list],
        bounds: Optional[list],
    ) -> tuple[np.ndarray, np.ndarray, str]:
        """Fit exponential model: y = a * exp(b * x) + c."""

        def exp_func(x, a, b, c):
            return a * np.exp(b * x) + c

        # Initial guess
        if initial_guess is None:
            a0 = (y_data[-1] - y_data[0]) / (np.exp(1) - 1)
            b0 = 1.0 / (x_data[-1] - x_data[0])
            c0 = y_data[0]
            initial_guess = [a0, b0, c0]

        # Fit
        if bounds:
            coeffs, _ = optimize.curve_fit(
                exp_func, x_data, y_data, p0=initial_guess, bounds=bounds
            )
        else:
            coeffs, _ = optimize.curve_fit(exp_func, x_data, y_data, p0=initial_guess)

        fitted_y = exp_func(x_data, *coeffs)
        equation = f"y = {coeffs[0]:.6g} * exp({coeffs[1]:.6g}x) + {coeffs[2]:.6g}"

        return coeffs, fitted_y, equation

    def _fit_logarithmic(
        self, x_data: np.ndarray, y_data: np.ndarray, initial_guess: Optional[list]
    ) -> tuple[np.ndarray, np.ndarray, str]:
        """Fit logarithmic model: y = a * log(x) + b."""

        def log_func(x, a, b):
            return a * np.log(x) + b

        # Initial guess
        if initial_guess is None:
            initial_guess = [1.0, 0.0]

        # Fit
        coeffs, _ = optimize.curve_fit(log_func, x_data, y_data, p0=initial_guess)
        fitted_y = log_func(x_data, *coeffs)
        equation = f"y = {coeffs[0]:.6g} * ln(x) + {coeffs[1]:.6g}"

        return coeffs, fitted_y, equation

    def _fit_power(
        self, x_data: np.ndarray, y_data: np.ndarray, initial_guess: Optional[list]
    ) -> tuple[np.ndarray, np.ndarray, str]:
        """Fit power law model: y = a * x^b."""

        def power_func(x, a, b):
            return a * np.power(x, b)

        # Initial guess
        if initial_guess is None:
            initial_guess = [1.0, 1.0]

        # Fit
        coeffs, _ = optimize.curve_fit(power_func, x_data, y_data, p0=initial_guess)
        fitted_y = power_func(x_data, *coeffs)
        equation = f"y = {coeffs[0]:.6g} * x^{coeffs[1]:.6g}"

        return coeffs, fitted_y, equation

    def _fit_sinusoidal(
        self, x_data: np.ndarray, y_data: np.ndarray, initial_guess: Optional[list]
    ) -> tuple[np.ndarray, np.ndarray, str]:
        """Fit sinusoidal model: y = a * sin(b * x + c) + d."""

        def sin_func(x, a, b, c, d):
            return a * np.sin(b * x + c) + d

        # Initial guess
        if initial_guess is None:
            a0 = (np.max(y_data) - np.min(y_data)) / 2
            d0 = np.mean(y_data)
            # Estimate frequency from FFT
            fft = np.fft.fft(y_data - d0)
            freqs = np.fft.fftfreq(len(y_data), x_data[1] - x_data[0])
            peak_freq = abs(freqs[np.argmax(np.abs(fft[1:])) + 1])
            b0 = 2 * np.pi * peak_freq
            c0 = 0.0
            initial_guess = [a0, b0, c0, d0]

        # Fit
        coeffs, _ = optimize.curve_fit(sin_func, x_data, y_data, p0=initial_guess)
        fitted_y = sin_func(x_data, *coeffs)
        equation = f"y = {coeffs[0]:.6g} * sin({coeffs[1]:.6g}x + {coeffs[2]:.6g}) + {coeffs[3]:.6g}"

        return coeffs, fitted_y, equation

    def _fit_gaussian(
        self, x_data: np.ndarray, y_data: np.ndarray, initial_guess: Optional[list]
    ) -> tuple[np.ndarray, np.ndarray, str]:
        """Fit Gaussian model: y = a * exp(-(x-b)^2 / (2*c^2)) + d."""

        def gaussian_func(x, a, b, c, d):
            return a * np.exp(-((x - b) ** 2) / (2 * c**2)) + d

        # Initial guess
        if initial_guess is None:
            a0 = np.max(y_data) - np.min(y_data)
            b0 = x_data[np.argmax(y_data)]
            c0 = (x_data[-1] - x_data[0]) / 4
            d0 = np.min(y_data)
            initial_guess = [a0, b0, c0, d0]

        # Fit
        coeffs, _ = optimize.curve_fit(gaussian_func, x_data, y_data, p0=initial_guess)
        fitted_y = gaussian_func(x_data, *coeffs)
        equation = f"y = {coeffs[0]:.6g} * exp(-((x-{coeffs[1]:.6g})^2) / (2*{coeffs[2]:.6g}^2)) + {coeffs[3]:.6g}"

        return coeffs, fitted_y, equation

    def _fit_custom(
        self,
        x_data: np.ndarray,
        y_data: np.ndarray,
        function_code: str,
        initial_guess: Optional[list],
        bounds: Optional[list],
    ) -> tuple[np.ndarray, np.ndarray, str]:
        """Fit custom function defined by user."""
        # Create function from code (sandboxed)
        # WARNING: This should be properly sandboxed in production
        import ast

        # Parse function definition
        try:
            tree = ast.parse(function_code)
            if not (
                len(tree.body) == 1 and isinstance(tree.body[0], ast.FunctionDef)
            ):
                raise ValueError("Custom function must be a single function definition")

            func_name = tree.body[0].name
            local_namespace = {}
            exec(function_code, {"np": np, "numpy": np}, local_namespace)
            custom_func = local_namespace[func_name]

        except Exception as e:
            raise ValueError(f"Error parsing custom function: {e}")

        # Fit
        if initial_guess is None:
            raise ValueError("Custom fit requires initial_guess")

        if bounds:
            coeffs, _ = optimize.curve_fit(
                custom_func, x_data, y_data, p0=initial_guess, bounds=bounds
            )
        else:
            coeffs, _ = optimize.curve_fit(custom_func, x_data, y_data, p0=initial_guess)

        fitted_y = custom_func(x_data, *coeffs)
        equation = f"Custom function with parameters: {coeffs}"

        return coeffs, fitted_y, equation

    def _calculate_r_squared(self, y_true: np.ndarray, y_pred: np.ndarray) -> float:
        """Calculate R² coefficient of determination."""
        ss_res = np.sum((y_true - y_pred) ** 2)
        ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)

        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

        return r_squared

    def predict(self, coeffs: np.ndarray, x_new: np.ndarray, fit_type: FitType) -> np.ndarray:
        """Predict y values for new x values using fit coefficients.

        Args:
            coeffs: Fit coefficients
            x_new: New x values
            fit_type: Type of fit

        Returns:
            Predicted y values
        """
        if fit_type == FitType.POLYNOMIAL or fit_type == FitType.LINEAR:
            return np.polyval(coeffs, x_new)
        elif fit_type == FitType.EXPONENTIAL:
            return coeffs[0] * np.exp(coeffs[1] * x_new) + coeffs[2]
        elif fit_type == FitType.LOGARITHMIC:
            return coeffs[0] * np.log(x_new) + coeffs[1]
        elif fit_type == FitType.POWER:
            return coeffs[0] * np.power(x_new, coeffs[1])
        elif fit_type == FitType.SINUSOIDAL:
            return coeffs[0] * np.sin(coeffs[1] * x_new + coeffs[2]) + coeffs[3]
        elif fit_type == FitType.GAUSSIAN:
            return coeffs[0] * np.exp(-((x_new - coeffs[1]) ** 2) / (2 * coeffs[2] ** 2)) + coeffs[3]
        else:
            raise ValueError(f"Prediction not supported for {fit_type}")
