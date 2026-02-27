import yaml
from app.odoo_client import OdooClient

def main():
    with open("config.yaml", "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    exempt_ids = cfg.get("exemptions", {}).get("limited_rules_employee_ids", [])

    if not exempt_ids:
        print("Nessun employee_id in limited_rules_employee_ids")
        return

    client = OdooClient(
        url=cfg["odoo"]["url"],
        db=cfg["odoo"]["db"],
        user=cfg["odoo"]["user"],
        password=cfg["odoo"]["password"],
        timezone=cfg["timezone"],
    )

    names = client.get_employee_names_by_ids(exempt_ids)

    print("\nEmployee esclusi dalle regole (limited_rules_employee_ids):\n")
    for emp_id in exempt_ids:
        name = names.get(emp_id, "⚠️ ID NON TROVATO")
        print(f"- {emp_id}: {name}")

if __name__ == "__main__":
    main()
