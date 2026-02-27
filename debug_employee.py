import yaml
from app.odoo_client import OdooClient

with open("config.yaml", "r", encoding="utf-8") as f:
    cfg = yaml.safe_load(f)

client = OdooClient(
    url=cfg["odoo"]["url"],
    db=cfg["odoo"]["db"],
    user=cfg["odoo"]["user"],
    password=cfg["odoo"]["password"],
    timezone=cfg["timezone"],
)

matches = client.search_employees("Marco Tucceri")
print(matches)
active = client.fetch_active_employees()
print("Marco 106 presente tra gli active?", any(emp_id == 106 for emp_id, _ in active))
d = {emp_id: name for emp_id, name in active}
print("Nome per 106:", d.get(106))
