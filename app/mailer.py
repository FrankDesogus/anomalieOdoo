import mimetypes
import smtplib
from pathlib import Path
from email.message import EmailMessage


def send_mail(subject: str, body: str, mail_cfg: dict, attachments: list[str] | None = None):
    msg = EmailMessage()
    msg["From"] = mail_cfg["from"]
    msg["To"] = ", ".join(mail_cfg["to"])
    msg["Subject"] = subject
    msg.set_content(body)

    for attachment in attachments or []:
        path = Path(attachment)
        data = path.read_bytes()
        mime_type, _ = mimetypes.guess_type(path.name)

        if mime_type:
            maintype, subtype = mime_type.split("/", 1)
        else:
            maintype, subtype = "application", "octet-stream"

        msg.add_attachment(
            data,
            maintype=maintype,
            subtype=subtype,
            filename=path.name,
        )

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
