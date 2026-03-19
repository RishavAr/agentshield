from datetime import UTC, datetime

from agentshield.policy.anomaly_detector import AnomalyDetector


def test_velocity_anomaly() -> None:
    detector = AnomalyDetector()
    alerts = []
    for i in range(30):
        ts = datetime(2026, 1, 1, 12, i % 10, 0, tzinfo=UTC)
        detector.analyze("agent-1", "tool", 0.2, timestamp=ts)
    spike = datetime(2026, 1, 1, 13, 0, 0, tzinfo=UTC)
    for _ in range(30):
        alerts = detector.analyze("agent-1", "tool", 0.2, timestamp=spike)
    assert any(a.type == "velocity" for a in alerts)


def test_tool_anomaly() -> None:
    detector = AnomalyDetector()
    detector.analyze("agent-1", "tool-a", 0.2)
    alerts = detector.analyze("agent-1", "tool-b", 0.2)
    assert any(a.type == "tool" for a in alerts)


def test_time_anomaly() -> None:
    detector = AnomalyDetector()
    alerts = detector.analyze("agent-1", "tool", 0.2, timestamp=datetime(2026, 1, 1, 2, 0, tzinfo=UTC))
    assert any(a.type == "time" for a in alerts)


def test_pattern_and_escalation_anomaly() -> None:
    detector = AnomalyDetector()
    for _ in range(15):
        detector.analyze("agent-1", "same_tool", 0.1)
    alerts = detector.analyze("agent-1", "same_tool", 0.95)
    types = {a.type for a in alerts}
    assert "pattern" in types or "escalation" in types
