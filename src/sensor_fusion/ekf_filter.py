"""Extended Kalman filter for fused tactical track estimation."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

LOGGER = logging.getLogger(__name__)

try:
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover
    np = None  # type: ignore


class EKFFilter:
    """3D position/velocity tracker for contested battlespace motion prediction.

    State vector x:
      [x, y, z, vx, vy, vz]
    where:
      - position components represent target location in mission coordinate frame.
      - velocity components represent tactical movement trend for intercept planning.

    Matrices:
      - P (covariance): uncertainty in current state estimate.
      - Q (process noise): maneuver unpredictability/noise from battlefield dynamics.
      - R (measurement noise): sensor uncertainty from EO/RADAR/LIDAR observations.
    """

    def __init__(self, dt: float = 0.1, process_noise: float = 1.0, measurement_noise: float = 0.5) -> None:
        if not isinstance(dt, (int, float)) or dt <= 0:
            raise ValueError("dt must be a positive number")
        if not isinstance(process_noise, (int, float)) or process_noise <= 0:
            raise ValueError("process_noise must be a positive number")
        if not isinstance(measurement_noise, (int, float)) or measurement_noise <= 0:
            raise ValueError("measurement_noise must be a positive number")

        self.dt = float(dt)
        self.process_noise = float(process_noise)
        self.measurement_noise = float(measurement_noise)
        self.numpy_available = np is not None

        self._history: List[List[float]] = []
        self._max_history = 10

        if self.numpy_available:
            self.F = np.eye(6)  # type: ignore[union-attr]
            self.F[0, 3] = self.dt
            self.F[1, 4] = self.dt
            self.F[2, 5] = self.dt

            self.H = np.zeros((3, 6))  # type: ignore[union-attr]
            self.H[0, 0] = 1.0
            self.H[1, 1] = 1.0
            self.H[2, 2] = 1.0

            self.Q = np.eye(6) * self.process_noise  # type: ignore[union-attr]
            self.R = np.eye(3) * self.measurement_noise  # type: ignore[union-attr]
            self.P = np.eye(6) * 10.0  # type: ignore[union-attr]
            self.x = np.zeros((6, 1))  # type: ignore[union-attr]
        else:
            LOGGER.warning("NumPy unavailable; EKFFilter using moving-average fallback")
            self.x = [0.0] * 6
            self.P = [[10.0 if i == j else 0.0 for j in range(6)] for i in range(6)]

    def predict(self):
        """Propagate state with constant velocity assumption."""
        if self.numpy_available:
            self.x = self.F @ self.x  # type: ignore[operator]
            self.P = self.F @ self.P @ self.F.T + self.Q  # type: ignore[operator]
            return self.x.copy()

        self.x[0] += self.x[3] * self.dt
        self.x[1] += self.x[4] * self.dt
        self.x[2] += self.x[5] * self.dt
        return list(self.x)

    def update(self, measurement):
        """Incorporate 3D position measurement into current track estimate."""
        if self.numpy_available:
            z = np.asarray(measurement, dtype=float).reshape(3, 1)  # type: ignore[union-attr]
            y = z - (self.H @ self.x)
            s = self.H @ self.P @ self.H.T + self.R
            k = self.P @ self.H.T @ np.linalg.inv(s)  # type: ignore[union-attr]
            self.x = self.x + (k @ y)
            i = np.eye(6)  # type: ignore[union-attr]
            self.P = (i - (k @ self.H)) @ self.P
            return self.x.copy()

        measurement_list = [float(v) for v in measurement]
        if len(measurement_list) != 3:
            raise ValueError("measurement must contain 3 values")
        self._history.append(measurement_list)
        if len(self._history) > self._max_history:
            self._history.pop(0)
        avg = [sum(values) / len(values) for values in zip(*self._history)]
        old_pos = self.x[:3]
        self.x[:3] = avg
        self.x[3] = (self.x[0] - old_pos[0]) / self.dt
        self.x[4] = (self.x[1] - old_pos[1]) / self.dt
        self.x[5] = (self.x[2] - old_pos[2]) / self.dt
        return list(self.x)

    def get_state(self) -> Dict[str, Any]:
        """Return fused state for downstream track management and tactical display."""
        if self.numpy_available:
            values = self.x.flatten().tolist()
            covariance = self.P.tolist()
        else:
            values = list(self.x)
            covariance = self.P
        return {
            "position": tuple(values[:3]),
            "velocity": tuple(values[3:6]),
            "covariance": covariance,
        }

    def reset(self, initial_state: Optional[List[float]] = None) -> None:
        """Reset filter state when track lifecycle restarts."""
        if initial_state is not None:
            if not isinstance(initial_state, list) or len(initial_state) != 6:
                raise ValueError("initial_state must be a list of 6 floats")
            state_values = [float(v) for v in initial_state]
        else:
            state_values = [0.0] * 6

        if self.numpy_available:
            self.x = np.asarray(state_values, dtype=float).reshape(6, 1)  # type: ignore[union-attr]
            self.P = np.eye(6) * 10.0  # type: ignore[union-attr]
        else:
            self.x = state_values
            self.P = [[10.0 if i == j else 0.0 for j in range(6)] for i in range(6)]
            self._history.clear()
