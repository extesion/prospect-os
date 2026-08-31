import sys
import os

# Add root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.database.connection import SessionLocal, engine, Base
from backend.database.models import User
from backend.security.auth import get_password_hash

def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        users = [
            {"name": "Carlos Silva", "email": "carlos@prospector.com", "password": "123"},
            {"name": "Maria Oliveira", "email": "maria@prospector.com", "password": "123"},
            {"name": "João Santos", "email": "joao@prospector.com", "password": "123"},
            {"name": "Ana Paula", "email": "ana@prospector.com", "password": "123"},
        ]

        created_count = 0
        for u in users:
            existing = db.query(User).filter(User.email == u["email"]).first()
            if not existing:
                new_user = User(
                    name=u["name"],
                    email=u["email"],
                    password_hash=get_password_hash(u["password"]),
                    active=True
                )
                db.add(new_user)
                created_count += 1

        db.commit()
        print(f"[SUCCESS] Seed concluído! {created_count} usuários criados.")
        print("Usuários padrão disponíveis (Senha: 123):")
        for u in users:
            print(f"  - {u['name']} ({u['email']})")
    except Exception as e:
        db.rollback()
        print(f"[ERROR] Falha no seed: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    seed()
