import smtplib
from email.message import EmailMessage

def send_mail(subject: str, body: str, mail_cfg: dict):
    msg = EmailMessage()
    msg["From"] = mail_cfg["from"]
    msg["To"] = ", ".join(mail_cfg["to"])
    msg["Subject"] = subject
    msg.set_content(body)

    with smtplib.SMTP(mail_cfg["smtp_host"], mail_cfg["smtp_port"], timeout=30) as server:
        server.ehlo()
        if mail_cfg.get("starttls", True):
            server.starttls()
            server.ehlo()

        username = (mail_cfg.get("username") or "").strip()
        password = (mail_cfg.get("password") or "").strip()
        if username and password:
            server.login(username, password)

        server.send_message(msg)
