import sys
import os
import json

# Add root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.database.connection import SessionLocal, engine, Base
import backend.database.models # Ensure all models are registered with Base.metadata
import qualifier.models.qualification_result # Ensure qualifier models are registered with Base.metadata
from backend.database.models import User, CycleSetting
from backend.security.auth import get_password_hash

def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        users = [
            {"name": "Carlos Silva", "email": "carlos@prospector.com", "password": "123", "role": "ADMIN"},
            {"name": "Maria Oliveira", "email": "maria@prospector.com", "password": "123", "role": "USER"},
            {"name": "João Santos", "email": "joao@prospector.com", "password": "123", "role": "USER"},
            {"name": "Ana Paula", "email": "ana@prospector.com", "password": "123", "role": "USER"},
        ]

        created_count = 0
        for u in users:
            existing = db.query(User).filter(User.email == u["email"]).first()
            if not existing:
                new_user = User(
                    name=u["name"],
                    email=u["email"],
                    password_hash=get_password_hash(u["password"]),
                    role=u.get("role", "USER"),
                    active=True,
                    is_deleted=False
                )
                db.add(new_user)
                created_count += 1
            else:
                existing.role = u.get("role", "USER")
                existing.active = True
                existing.is_deleted = False

        default_presets = [
            {"id": "8H", "name": "Ciclo 8 Horas", "hours": 8.0, "target": 160, "rate": 20.0},
            {"id": "6H", "name": "Ciclo 6 Horas", "hours": 6.0, "target": 160, "rate": 26.7},
            {"id": "CUSTOM", "name": "Personalizado", "hours": 8.0, "target": 160, "rate": 20.0}
        ]

        cycle_cfg = db.query(CycleSetting).first()
        if not cycle_cfg:
            db.add(CycleSetting(default_daily_target=160, presets_json=json.dumps(default_presets)))
        elif not cycle_cfg.presets_json:
            cycle_cfg.presets_json = json.dumps(default_presets)

        db.commit()
        print(f"[SUCCESS] Seed concluído! {created_count} usuários criados.")
        print("Usuários padrão disponíveis (Senha: 123):")
        for u in users:
            print(f"  - {u['name']} ({u['email']}) [{u['role']}]")
    except Exception as e:
        db.rollback()
        print(f"[ERROR] Falha no seed: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    seed()
