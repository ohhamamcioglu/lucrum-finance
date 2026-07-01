"""
make_admin.py — Bir kullanıcıyı admin yapar (ilk admin'i yetkilendirmek için).

Self-servis bir "beni admin yap" API endpoint'i kasıtlı olarak yok (güvenlik riski).
Bunun yerine bu script'i çalıştır:

    python make_admin.py <email>

Docker içinde:

    docker compose exec backend python make_admin.py <email>

Postgres'e doğrudan erişimin varsa (script'i çalıştıramıyorsan) alternatif:

    UPDATE users SET is_admin = true WHERE email = '<email>';
"""
import sys

from db_models import SessionLocal, DBUser


def make_admin(email: str) -> None:
    session = SessionLocal()
    try:
        email_clean = email.lower().strip()
        user = session.query(DBUser).filter(DBUser.email == email_clean).first()
        if not user:
            print(f"Hata: '{email_clean}' e-posta adresiyle kayıtlı bir kullanıcı bulunamadı.")
            sys.exit(1)
        if user.is_admin:
            print(f"'{email_clean}' zaten admin.")
            return
        user.is_admin = True
        session.commit()
        print(f"'{email_clean}' artık admin (id={user.id}).")
    finally:
        session.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Kullanım: python make_admin.py <email>")
        sys.exit(1)
    make_admin(sys.argv[1])
