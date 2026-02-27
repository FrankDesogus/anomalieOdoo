import argparse
import yaml
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.detector import detect_for_day
from app.fake_data import build_fake_sessions
from app.dedup import DedupStore
from app.mailer import send_mail
from app.odoo_client import OdooClient


def day_range_utc(day: date, tz_name: str):
    tz = ZoneInfo(tz_name)
    start_local = datetime.combine(day, time(0, 0)).replace(tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    start_utc = start_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    end_utc = end_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    return start_utc.strftime("%Y-%m-%d %H:%M:%S"), end_utc.strftime("%Y-%m-%d %H:%M:%S")


def format_anomalies(anomalies):
    lines = []

    def friendly_line(a):
        day_s = str(a.day)

        if a.code == "LATE_CHECKIN":
            # usa evidence se c'è, altrimenti fallback sul testo già pronto
            t = None
            if isinstance(a.evidence, dict) and a.evidence.get("first_check_in"):
                # "2026-01-20T09:02:00+01:00" -> prendo HH:MM
                t = a.evidence["first_check_in"][11:16]
            if t:
                msg = f"Timbratura alle {t} (oltre le 09:00). Probabile ritardo o dimenticanza."
            else:
                msg = a.message + " Probabile ritardo o dimenticanza."

        elif a.code == "NO_CHECKIN_BY_0900":
            msg = "Nessuna timbratura di ingresso entro le 09:00. Probabile assenza o dimenticanza."

        elif a.code == "LUNCH_LATE_RETURN":
            msg = a.message + " Probabile rientro tardivo o mancata timbratura."

        elif a.code == "LUNCH_NO_RETURN":
            msg = a.message + " Probabile mancata timbratura di rientro."

        elif a.code == "AUTO_CLOSE_LATE":
            msg = a.message  # già user-friendly

        elif a.code == "NO_ATTENDANCE_ALL_DAY":
            msg = a.message  # già user-friendly

        else:
            # fallback generico
            msg = a.message

        return f"{a.employee_name}  {day_s}  {msg}"

    for a in anomalies:
        lines.append(friendly_line(a))

    return "\n".join(lines)


def month_days(yyyy_mm: str) -> list[date]:
    y_s, m_s = yyyy_mm.split("-")
    y, m = int(y_s), int(m_s)
    start = date(y, m, 1)
    if m == 12:
        end = date(y + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(y, m + 1, 1) - timedelta(days=1)
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def build_days_to_check(args) -> list[date]:
    today = date.today()

    if args.mode == "ops":
        # oggi + lookback (default 1 = ieri)
        n = max(0, int(args.lookback_days))
        return [today - timedelta(days=i) for i in range(n + 1)]

    if args.mode == "day":
        if not args.day:
            raise RuntimeError("mode=day richiede --day YYYY-MM-DD")
        d = date.fromisoformat(args.day)
        return [d - timedelta(days=1), d] if args.also_prev else [d]

    if args.mode == "month":
        if not args.month:
            raise RuntimeError("mode=month richiede --month YYYY-MM")
        return month_days(args.month)

    raise RuntimeError("mode non valido")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["ops", "day", "month"], default="ops",
                        help="ops=oggi+ieri, day=un giorno, month=intero mese")
    parser.add_argument("--lookback-days", type=int, default=1,
                        help="Solo per mode=ops: quanti giorni indietro includere (default 1 = ieri)")
    parser.add_argument("--day", default=None, help="YYYY-MM-DD (richiesto se mode=day)")
    parser.add_argument("--also-prev", action="store_true",
                        help="Se mode=day, include anche il giorno precedente")
    parser.add_argument("--month", default=None, help="YYYY-MM (richiesto se mode=month)")
    parser.add_argument("--send-mail", action="store_true", help="Invia email (se mail.enabled=true)")
    parser.add_argument("--no-dedup", action="store_true",
                        help="Non usare deduplica (utile per report mese/giorno)")
    args = parser.parse_args()

    with open("config.yaml", "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    days = sorted(build_days_to_check(args))

    # In ODOO mode: crea client una sola volta
    client = None
    if cfg["mode"].upper() == "ODOO":
        o = cfg["odoo"]
        client = OdooClient(o["url"], o["db"], o["user"], o["password"], cfg["timezone"])

    all_anomalies = []

    for d in days:
        # 🚫 Salta sabato e domenica
        if d.weekday() >= 5:
            print(f"Skip weekend: {d}")
            continue

        # 1) carica sessioni
        if cfg["mode"].upper() == "FAKE":
            sessions = build_fake_sessions(d, cfg["timezone"])
        elif cfg["mode"].upper() == "ODOO":
            start_utc, end_utc = day_range_utc(d, cfg["timezone"])
            sessions = client.fetch_sessions_for_day(start_utc, end_utc)
            employees = client.fetch_active_employees()
        else:
            raise RuntimeError("config.yaml: mode deve essere FAKE o ODOO")

        # 2) detect
        if cfg["mode"].upper() == "ODOO":
            anomalies = detect_for_day(d, sessions, cfg, employees=employees)  # <-- passiamo employees
        else:
            anomalies = detect_for_day(d, sessions, cfg)

        all_anomalies.extend(anomalies)

    # Dedup:
    # - operativo (ops): di default ON
    # - report (day/month): di default OFF
    use_dedup = (args.mode == "ops") and (not args.no_dedup)

    fresh = all_anomalies
    if use_dedup:
        store = DedupStore("anomalies.db")
        store.init()
        tmp = []
        for a in all_anomalies:
            key_day = str(a.day)
            if not store.already_sent(key_day, a.employee_id, a.code):
                store.mark_sent(key_day, a.employee_id, a.code)
                tmp.append(a)
        fresh = tmp

    if not fresh:
        print("Nessuna anomalia trovata.")
        return


    # --- Soppressione NO_CHECKIN se già c'è NO_ATTENDANCE_ALL_DAY (pomeriggio o giorni passati) ---
    tz = ZoneInfo(cfg["timezone"])
    now_local = datetime.now(tz)
    today_local = now_local.date()

    cutoff_str = cfg.get("rules", {}).get("suppress_no_checkin_if_absent_after", "14:30")
    cutoff_h, cutoff_m = map(int, cutoff_str.split(":"))
    after_cutoff = (now_local.hour, now_local.minute) >= (cutoff_h, cutoff_m)

    # chiavi (day, employee_id) per cui esiste assenza tutto il giorno
    absent_all_day_keys = {(a.day, a.employee_id) for a in fresh if a.code == "NO_ATTENDANCE_ALL_DAY"}

    filtered = []
    for a in fresh:
        # Se è un NO_CHECKIN, lo togliamo quando:
        # - lo stesso dipendente/giorno è già marcato come assente tutto il giorno
        # - e (è un giorno passato) oppure (oggi e siamo dopo il cutoff)
        if a.code == "NO_CHECKIN_BY_0900" and (a.day, a.employee_id) in absent_all_day_keys:
            if (a.day < today_local) or (a.day == today_local and after_cutoff):
                continue
        filtered.append(a)

    fresh = filtered
    # --- fine soppressione ---

    # ordina output
    fresh.sort(key=lambda a: (a.day, a.employee_name, a.code))

    body = format_anomalies(fresh)
    print(body)

    # email opzionale
    mail_cfg = cfg.get("mail", {})
    if args.send_mail and mail_cfg.get("enabled", False):
        send_mail(
            subject=f"Odoo – {len(fresh)} anomalie ({days[0]} → {days[-1]})",
            body=body,
            mail_cfg=mail_cfg
        )
        print("\nEmail inviata.")


if __name__ == "__main__":
    main()
