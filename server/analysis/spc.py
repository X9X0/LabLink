"""Statistical Process Control (SPC) analysis module."""

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
from scipy import stats

from .models import (CapabilityResult, SPCChartConfig, SPCChartResult,
                     SPCChartType)

logger = logging.getLogger(__name__)


class SPCAnalyzer:
    """Statistical Process Control analyzer."""

    # Control chart constants
    A2_CONSTANTS = {  # X-bar chart (R-based)
        2: 1.880,
        3: 1.023,
        4: 0.729,
        5: 0.577,
        6: 0.483,
        7: 0.419,
        8: 0.373,
        9: 0.337,
        10: 0.308,
    }

    D3_CONSTANTS = {  # R chart LCL
        2: 0,
        3: 0,
        4: 0,
        5: 0,
        6: 0,
        7: 0.076,
        8: 0.136,
        9: 0.184,
        10: 0.223,
    }

    D4_CONSTANTS = {  # R chart UCL
        2: 3.267,
        3: 2.574,
        4: 2.282,
        5: 2.114,
        6: 2.004,
        7: 1.924,
        8: 1.864,
        9: 1.816,
        10: 1.777,
    }

    def __init__(self):
        """Initialize SPC analyzer."""
        pass

    def generate_control_chart(
        self, data: np.ndarray, config: SPCChartConfig
    ) -> SPCChartResult:
        """Generate control chart.

        Args:
            data: Process data
            config: Chart configuration

        Returns:
            SPCChartResult with control limits and violations
        """
        chart_type = config.chart_type

        if chart_type == SPCChartType.XBAR_R:
            return self._xbar_r_chart(data, config)
        elif chart_type == SPCChartType.XBAR_S:
            return self._xbar_s_chart(data, config)
        elif chart_type == SPCChartType.INDIVIDUALS:
            return self._individuals_chart(data, config)
        elif chart_type == SPCChartType.P_CHART:
            return self._p_chart(data, config)
        elif chart_type == SPCChartType.C_CHART:
            return self._c_chart(data, config)
        elif chart_type == SPCChartType.U_CHART:
            return self._u_chart(data, config)
        else:
            raise ValueError(f"Unsupported chart type: {chart_type}")

    def _xbar_r_chart(self, data: np.ndarray, config: SPCChartConfig) -> SPCChartResult:
        """Generate X-bar and R control chart.

        Args:
            data: Process data (flattened or 2D subgroups)
            config: Chart configuration

        Returns:
            SPCChartResult for X-bar chart
        """
        subgroup_size = config.subgroup_size

        # Reshape data into subgroups
        num_subgroups = len(data) // subgroup_size
        subgroups = data[: num_subgroups * subgroup_size].reshape(
            num_subgroups, subgroup_size
        )

        # Calculate subgroup means and ranges
        xbar_values = np.mean(subgroups, axis=1)
        r_values = np.max(subgroups, axis=1) - np.min(subgroups, axis=1)

        # Calculate center lines
        xbar_center = np.mean(xbar_values)
        r_center = np.mean(r_values)

        # Get constants
        if subgroup_size not in self.A2_CONSTANTS:
            raise ValueError(f"Subgroup size {subgroup_size} not supported (2-10)")

        A2 = self.A2_CONSTANTS[subgroup_size]

        # Calculate control limits for X-bar chart
        ucl = xbar_center + A2 * r_center
        lcl = xbar_center - A2 * r_center

        # Detect out-of-control points
        out_of_control = self._detect_out_of_control(xbar_values, xbar_center, ucl, lcl)

        # Check control rules
        violations = self._check_control_rules(xbar_values, xbar_center, ucl, lcl)

        return SPCChartResult(
            chart_type=SPCChartType.XBAR_R,
            center_line=float(xbar_center),
            ucl=float(ucl),
            lcl=float(lcl),
            subgroup_values=xbar_values.tolist(),
            out_of_control_points=out_of_control,
            violations=violations,
        )

    def _xbar_s_chart(self, data: np.ndarray, config: SPCChartConfig) -> SPCChartResult:
        """Generate X-bar and S (standard deviation) control chart."""
        subgroup_size = config.subgroup_size

        # Reshape data into subgroups
        num_subgroups = len(data) // subgroup_size
        subgroups = data[: num_subgroups * subgroup_size].reshape(
            num_subgroups, subgroup_size
        )

        # Calculate subgroup means and standard deviations
        xbar_values = np.mean(subgroups, axis=1)
        s_values = np.std(subgroups, axis=1, ddof=1)

        # Calculate center lines
        xbar_center = np.mean(xbar_values)
        s_center = np.mean(s_values)

        # Constants for S chart (approximation)
        c4 = 0.7979  # For n>=25, c4 ≈ 1
        if subgroup_size < 25:
            c4 = np.sqrt(2 / (subgroup_size - 1)) * (
                stats.gamma(subgroup_size / 2) / stats.gamma((subgroup_size - 1) / 2)
            )

        A3 = 3 / (c4 * np.sqrt(subgroup_size))

        # Calculate control limits
        ucl = xbar_center + A3 * s_center
        lcl = xbar_center - A3 * s_center

        # Detect violations
        out_of_control = self._detect_out_of_control(xbar_values, xbar_center, ucl, lcl)
        violations = self._check_control_rules(xbar_values, xbar_center, ucl, lcl)

        return SPCChartResult(
            chart_type=SPCChartType.XBAR_S,
            center_line=float(xbar_center),
            ucl=float(ucl),
            lcl=float(lcl),
            subgroup_values=xbar_values.tolist(),
            out_of_control_points=out_of_control,
            violations=violations,
        )

    def _individuals_chart(
        self, data: np.ndarray, config: SPCChartConfig
    ) -> SPCChartResult:
        """Generate Individuals (I-MR) control chart."""
        # Calculate moving ranges
        moving_ranges = np.abs(np.diff(data))
        mr_center = np.mean(moving_ranges)

        # Constants for individuals chart
        d2 = 1.128  # For moving range of 2

        # Calculate control limits
        center_line = np.mean(data)
        ucl = center_line + 3 * (mr_center / d2)
        lcl = center_line - 3 * (mr_center / d2)

        # Detect violations
        out_of_control = self._detect_out_of_control(data, center_line, ucl, lcl)
        violations = self._check_control_rules(data, center_line, ucl, lcl)

        return SPCChartResult(
            chart_type=SPCChartType.INDIVIDUALS,
            center_line=float(center_line),
            ucl=float(ucl),
            lcl=float(lcl),
            subgroup_values=data.tolist(),
            out_of_control_points=out_of_control,
            violations=violations,
        )

    def _p_chart(self, data: np.ndarray, config: SPCChartConfig) -> SPCChartResult:
        """Generate P (proportion) control chart for defect rates."""
        # Data should be defect counts per subgroup
        subgroup_size = config.subgroup_size
        proportions = data / subgroup_size

        # Calculate center line
        p_bar = np.mean(proportions)

        # Calculate control limits
        std = np.sqrt(p_bar * (1 - p_bar) / subgroup_size)
        ucl = p_bar + 3 * std
        lcl = max(0, p_bar - 3 * std)  # Proportion can't be negative

        # Detect violations
        out_of_control = self._detect_out_of_control(proportions, p_bar, ucl, lcl)
        violations = self._check_control_rules(proportions, p_bar, ucl, lcl)

        return SPCChartResult(
            chart_type=SPCChartType.P_CHART,
            center_line=float(p_bar),
            ucl=float(ucl),
            lcl=float(lcl),
            subgroup_values=proportions.tolist(),
            out_of_control_points=out_of_control,
            violations=violations,
        )

    def _c_chart(self, data: np.ndarray, config: SPCChartConfig) -> SPCChartResult:
        """Generate C (count) control chart for defects per unit."""
        # Calculate center line (average defects per unit)
        c_bar = np.mean(data)

        # Calculate control limits
        std = np.sqrt(c_bar)
        ucl = c_bar + 3 * std
        lcl = max(0, c_bar - 3 * std)  # Count can't be negative

        # Detect violations
        out_of_control = self._detect_out_of_control(data, c_bar, ucl, lcl)
        violations = self._check_control_rules(data, c_bar, ucl, lcl)

        return SPCChartResult(
            chart_type=SPCChartType.C_CHART,
            center_line=float(c_bar),
            ucl=float(ucl),
            lcl=float(lcl),
            subgroup_values=data.tolist(),
            out_of_control_points=out_of_control,
            violations=violations,
        )

    def _u_chart(self, data: np.ndarray, config: SPCChartConfig) -> SPCChartResult:
        """Generate U (defects per unit) control chart."""
        # Data should be defects per sample, with variable sample sizes
        subgroup_size = config.subgroup_size

        # Calculate u values (defects per unit)
        u_values = data / subgroup_size

        # Calculate center line
        u_bar = np.mean(u_values)

        # Calculate control limits
        std = np.sqrt(u_bar / subgroup_size)
        ucl = u_bar + 3 * std
        lcl = max(0, u_bar - 3 * std)

        # Detect violations
        out_of_control = self._detect_out_of_control(u_values, u_bar, ucl, lcl)
        violations = self._check_control_rules(u_values, u_bar, ucl, lcl)

        return SPCChartResult(
            chart_type=SPCChartType.U_CHART,
            center_line=float(u_bar),
            ucl=float(ucl),
            lcl=float(lcl),
            subgroup_values=u_values.tolist(),
            out_of_control_points=out_of_control,
            violations=violations,
        )

    def _detect_out_of_control(
        self, values: np.ndarray, center: float, ucl: float, lcl: float
    ) -> List[int]:
        """Detect points outside control limits."""
        out_of_control = []

        for i, value in enumerate(values):
            if value > ucl or value < lcl:
                out_of_control.append(i)

        return out_of_control

    def _check_control_rules(
        self, values: np.ndarray, center: float, ucl: float, lcl: float
    ) -> List[str]:
        """Check Western Electric / Nelson rules for control chart violations."""
        violations = []

        # Rule 1: Point beyond 3-sigma (already detected in out_of_control)

        # Rule 2: 2 out of 3 consecutive points beyond 2-sigma
        sigma = (ucl - center) / 3
        upper_2sigma = center + 2 * sigma
        lower_2sigma = center - 2 * sigma

        for i in range(len(values) - 2):
            window = values[i : i + 3]
            beyond_2sigma = np.sum((window > upper_2sigma) | (window < lower_2sigma))
            if beyond_2sigma >= 2:
                violations.append(f"Rule 2 violation at points {i}-{i+2}")

        # Rule 3: 4 out of 5 consecutive points beyond 1-sigma
        upper_1sigma = center + sigma
        lower_1sigma = center - sigma

        for i in range(len(values) - 4):
            window = values[i : i + 5]
            beyond_1sigma = np.sum((window > upper_1sigma) | (window < lower_1sigma))
            if beyond_1sigma >= 4:
                violations.append(f"Rule 3 violation at points {i}-{i+4}")

        # Rule 4: 8 consecutive points on one side of center
        for i in range(len(values) - 7):
            window = values[i : i + 8]
            if np.all(window > center) or np.all(window < center):
                violations.append(f"Rule 4 violation at points {i}-{i+7}")

        return violations

    def calculate_capability(
        self,
        data: np.ndarray,
        lsl: Optional[float] = None,
        usl: Optional[float] = None,
        target: Optional[float] = None,
    ) -> CapabilityResult:
        """Calculate process capability indices.

        Args:
            data: Process data
            lsl: Lower specification limit
            usl: Upper specification limit
            target: Target value

        Returns:
            CapabilityResult with capability indices
        """
        mean = np.mean(data)
        std_dev = np.std(data, ddof=1)

        # Initialize result
        result = CapabilityResult(
            mean=float(mean),
            std_dev=float(std_dev),
            lsl=lsl,
            usl=usl,
            target=target,
            capability_assessment="",
        )

        # Calculate Cp (potential capability)
        if lsl is not None and usl is not None:
            cp = (usl - lsl) / (6 * std_dev)
            result.cp = float(cp)

            # Calculate Cpk (actual capability)
            cpu = (usl - mean) / (3 * std_dev)
            cpl = (mean - lsl) / (3 * std_dev)
            cpk = min(cpu, cpl)
            result.cpk = float(cpk)

            # Calculate Pp and Ppk (performance indices) - same as Cp/Cpk for long-term data
            result.pp = float(cp)
            result.ppk = float(cpk)

            # Calculate Cpm (Taguchi index) if target provided
            if target is not None:
                cpm = (usl - lsl) / (6 * np.sqrt(std_dev**2 + (mean - target) ** 2))
                result.cpm = float(cpm)

            # Estimate yield
            z_usl = (usl - mean) / std_dev
            z_lsl = (mean - lsl) / std_dev
            within_spec = stats.norm.cdf(z_usl) - stats.norm.cdf(-z_lsl)
            result.expected_within_spec = float(within_spec * 100)  # Percentage
            result.expected_defects_ppm = float((1 - within_spec) * 1e6)

            # Capability assessment
            if cpk >= 2.0:
                assessment = "Excellent capability (Cpk >= 2.0)"
            elif cpk >= 1.33:
                assessment = "Good capability (Cpk >= 1.33)"
            elif cpk >= 1.0:
                assessment = "Marginal capability (Cpk >= 1.0)"
            else:
                assessment = "Inadequate capability (Cpk < 1.0)"

            result.capability_assessment = assessment

        else:
            result.capability_assessment = (
                "Specification limits required for capability analysis"
            )

        return result
