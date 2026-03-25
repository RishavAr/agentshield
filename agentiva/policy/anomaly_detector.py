from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from statistics import mean, pstdev
from typing import Deque, Dict, List


@dataclass
class AnomalyAlert:
    type: str
    severity: str
    description: str

    def to_dict(self):
        return asdict(self)


class AnomalyDetector:
    """Detect suspicious agent behavior patterns."""

    def __init__(self):
        self._history: Dict[str, Deque[float]] = defaultdict(lambda: deque(maxlen=200))
        self._tools_seen: Dict[str, set] = defaultdict(set)
        self._last_actions: Dict[str, Deque[str]] = defaultdict(lambda: deque(maxlen=20))
        self._risk_history: Dict[str, Deque[float]] = defaultdict(lambda: deque(maxlen=50))

    def analyze(self, agent_id: str, tool_name: str, risk_score: float, timestamp: datetime | None = None, data_volume: int = 1) -> List[AnomalyAlert]:
        now = timestamp or datetime.now(UTC)
        alerts: List[AnomalyAlert] = []
        minute_marker = now.timestamp() // 60
        self._history[agent_id].append(minute_marker)
        self._risk_history[agent_id].append(risk_score)
        self._last_actions[agent_id].append(tool_name)

        alerts.extend(self._detect_velocity(agent_id))
        alerts.extend(self._detect_tool_anomaly(agent_id, tool_name))
        alerts.extend(self._detect_time_anomaly(now))
        alerts.extend(self._detect_pattern_anomaly(agent_id))
        alerts.extend(self._detect_escalation(agent_id))
        alerts.extend(self._detect_data_anomaly(data_volume))

        return alerts

    def _detect_velocity(self, agent_id: str) -> List[AnomalyAlert]:
        entries = list(self._history[agent_id])
        if len(entries) < 20:
            return []
        window = entries[-20:]
        current = sum(1 for x in window if x == window[-1])
        avg = mean([sum(1 for x in entries if x == bucket) for bucket in set(entries)])
        if current > avg * 2:
            return [AnomalyAlert("velocity", "high", f"Velocity spike detected: {current} req/min")]
        return []

    def _detect_tool_anomaly(self, agent_id: str, tool_name: str) -> List[AnomalyAlert]:
        if tool_name not in self._tools_seen[agent_id] and self._tools_seen[agent_id]:
            self._tools_seen[agent_id].add(tool_name)
            return [AnomalyAlert("tool", "medium", f"First-time tool usage: {tool_name}")]
        self._tools_seen[agent_id].add(tool_name)
        return []

    def _detect_time_anomaly(self, now: datetime) -> List[AnomalyAlert]:
        if now.hour < 6 or now.hour > 22:
            return [AnomalyAlert("time", "low", "Action executed at unusual hour")]
        return []

    def _detect_pattern_anomaly(self, agent_id: str) -> List[AnomalyAlert]:
        actions = list(self._last_actions[agent_id])
        if len(actions) >= 10 and len(set(actions[-10:])) == 1:
            return [AnomalyAlert("pattern", "high", f"Repeated action loop: {actions[-1]}")]
        return []

    def _detect_escalation(self, agent_id: str) -> List[AnomalyAlert]:
        risks = list(self._risk_history[agent_id])
        if len(risks) < 6:
            return []
        if risks[-1] > mean(risks[:-1]) + (pstdev(risks[:-1]) * 2 if len(risks[:-1]) > 1 else 0.2):
            return [AnomalyAlert("escalation", "high", "Risk scores trending upward")]
        return []

    def _detect_data_anomaly(self, data_volume: int) -> List[AnomalyAlert]:
        if data_volume > 10000:
            return [AnomalyAlert("data", "high", f"Unusually large data access volume: {data_volume}")]
        return []
