"""
Resend üzerinden transactional email gönderimi (email doğrulama, şifre sıfırlama).
RESEND_API_KEY tanımlı değilse dev fallback: email gönderilmez, link log'a yazılır.
"""
import os
import logging
import requests

logger = logging.getLogger("lucrum.email")

RESEND_API_KEY = os.getenv("RESEND_API_KEY")
FROM_EMAIL = os.getenv("RESEND_FROM_EMAIL", "Lucrum Finance <onboarding@resend.dev>")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

RESEND_API_URL = "https://api.resend.com/emails"


def _send(to_email: str, subject: str, html: str) -> None:
    if not RESEND_API_KEY:
        logger.warning("RESEND_API_KEY tanımlı değil (dev mod) — email gönderilmedi. To=%s Subject=%s", to_email, subject)
        logger.warning("Email içeriği (dev):\n%s", html)
        return

    resp = requests.post(
        RESEND_API_URL,
        headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
        json={"from": FROM_EMAIL, "to": [to_email], "subject": subject, "html": html},
        timeout=10,
    )
    if resp.status_code >= 300:
        logger.error("Resend email gönderimi başarısız: %s %s", resp.status_code, resp.text)


def send_verification_email(to_email: str, token: str) -> None:
    link = f"{FRONTEND_URL}/?verify-email={token}"
    html = f"""
    <p>Lucrum Finance hesabınızı doğrulamak için aşağıdaki bağlantıya tıklayın:</p>
    <p><a href="{link}">{link}</a></p>
    <p>Bu bağlantı {24} saat içinde geçerliliğini yitirir.</p>
    """
    _send(to_email, "Lucrum Finance — E-posta Doğrulama", html)


def send_password_reset_email(to_email: str, token: str) -> None:
    link = f"{FRONTEND_URL}/?reset-password={token}"
    html = f"""
    <p>Şifrenizi sıfırlamak için aşağıdaki bağlantıya tıklayın:</p>
    <p><a href="{link}">{link}</a></p>
    <p>Bu bağlantı 1 saat içinde geçerliliğini yitirir. Bu isteği siz yapmadıysanız bu emaili yok sayabilirsiniz.</p>
    """
    _send(to_email, "Lucrum Finance — Şifre Sıfırlama", html)
