from pathlib import Path

import yaml

from agentiva import Agentiva


TEMPLATES = ["healthcare", "finance", "ecommerce", "saas", "legal"]


def test_templates_exist_and_parse() -> None:
    for name in TEMPLATES:
        path = Path(f"policies/templates/{name}.yaml")
        assert path.exists()
        parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert "rules" in parsed


def test_templates_load_via_sdk_policy_argument() -> None:
    for name in TEMPLATES:
        shield = Agentiva(mode="shadow", policy=name)
        assert shield.policy_path is None or name in shield.policy_path


def test_finance_template_blocks_external_transfer_rule_present() -> None:
    parsed = yaml.safe_load(Path("policies/templates/finance.yaml").read_text(encoding="utf-8"))
    names = {rule["name"] for rule in parsed["rules"]}
    assert "block_external_account_transfer" in names


def test_saas_template_contains_db_migration_shadow() -> None:
    parsed = yaml.safe_load(Path("policies/templates/saas.yaml").read_text(encoding="utf-8"))
    names = {rule["name"] for rule in parsed["rules"]}
    assert "shadow_db_migrations" in names
