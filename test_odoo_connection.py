import yaml
from datetime import datetime
from app.odoo_client import OdooClient

def main():
    with open("config.yaml", "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    o = cfg["odoo"]
    client = OdooClient(
        url=o["url"],
        db=o["db"],
        user=o["user"],
        password=o["password"],
        timezone=cfg["timezone"],
    )

    print("OK: login admin riuscito")

    today = datetime.now().date()
    rows = client.fetch_attendances_for_day(today)

    print(f"Attendances trovate oggi: {len(rows)}")
    for r in rows[:10]:
        print(r)

if __name__ == "__main__":
    main()
