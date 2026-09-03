from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.database.connection import get_db
from backend.database.models import User, Channel, CollectionEvent, WorkSession, WorkSessionEvent, UserMusicConnection, utc_now
from backend.schemas.auth import UserAdminCreate, UserAdminUpdate, UserResponse
from backend.security.auth import get_password_hash, get_current_admin_user, verify_system_password

router = APIRouter(prefix="/users", tags=["Users (Admin Only)"])

@router.get("", response_model=List[UserResponse])
def list_users(
    db: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user)
):
    """Lista todos os usuários válidos e não excluídos (Exclusivo para ADMIN)."""
    users = (
        db.query(User)
        .filter(User.is_deleted == False)
        .order_by(User.id.asc())
        .all()
    )
    return [UserResponse.model_validate(u) for u in users]

@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user_admin(
    user_data: UserAdminCreate,
    db: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user)
):
    """Criação de novos usuários da equipe com hash seguro (Exclusivo para ADMIN)."""
    email_clean = user_data.email.lower().strip()
    existing = db.query(User).filter(User.email == email_clean, User.is_deleted == False).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"O e-mail '{email_clean}' já está cadastrado no sistema."
        )

    role_clean = user_data.role.upper().strip() if user_data.role else "USER"
    if role_clean not in ("ADMIN", "USER"):
        role_clean = "USER"

    # Se criar direto como ADMIN, validar senha mestra do sistema
    if role_clean == "ADMIN":
        if not verify_system_password(user_data.system_password):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Senha do sistema incorreta."
            )

    new_user = User(
        name=user_data.name.strip(),
        email=email_clean,
        password_hash=get_password_hash(user_data.password),
        role=role_clean,
        active=user_data.active,
        is_deleted=False,
        created_at=utc_now()
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return UserResponse.model_validate(new_user)

@router.put("/{user_id}", response_model=UserResponse)
def update_user_admin(
    user_id: int,
    update_data: UserAdminUpdate,
    db: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user)
):
    """Edição de usuário, promoção com senha mestra, proteção ao último admin e alteração de senha."""
    user = db.query(User).filter(User.id == user_id, User.is_deleted == False).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuário não encontrado."
        )

    # Contagem de administradores ativos e válidos
    active_admins_count = (
        db.query(User)
        .filter(User.role == "ADMIN", User.active == True, User.is_deleted == False)
        .count()
    )

    if update_data.name is not None:
        user.name = update_data.name.strip()
    
    if update_data.email is not None:
        email_clean = update_data.email.lower().strip()
        if email_clean != user.email:
            existing = db.query(User).filter(User.email == email_clean, User.is_deleted == False, User.id != user.id).first()
            if existing:
                raise HTTPException(status_code=400, detail="Este e-mail já está sendo utilizado por outro usuário.")
            user.email = email_clean

    if update_data.role is not None:
        role_clean = update_data.role.upper().strip()
        if role_clean in ("ADMIN", "USER"):
            # Promoção USER -> ADMIN exige senha do sistema
            if role_clean == "ADMIN" and user.role != "ADMIN":
                if not verify_system_password(update_data.system_password):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Senha do sistema incorreta."
                    )
                user.role = "ADMIN"
            # Rebaixamento ADMIN -> USER: Proteger último admin ativo
            elif role_clean == "USER" and user.role == "ADMIN":
                if active_admins_count <= 1:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="O sistema precisa possuir pelo menos um administrador."
                    )
                user.role = "USER"

    if update_data.active is not None:
        # Desativação de ADMIN: Proteger último admin ativo
        if not update_data.active and user.role == "ADMIN" and user.active and active_admins_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="O sistema precisa possuir pelo menos um administrador."
            )
        user.active = update_data.active

    if update_data.password and update_data.password.strip():
        user.password_hash = get_password_hash(update_data.password.strip())

    db.commit()
    db.refresh(user)
    return UserResponse.model_validate(user)

@router.delete("/{user_id}")
def delete_user_admin(
    user_id: int,
    db: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user)
):
    """Remove um usuário do sistema (Exclusivo para ADMIN, com proteção contra órfãos e último admin)."""
    user = db.query(User).filter(User.id == user_id, User.is_deleted == False).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")

    # Proteção ao último admin do sistema
    if user.role == "ADMIN":
        active_admins_count = (
            db.query(User)
            .filter(User.role == "ADMIN", User.active == True, User.is_deleted == False)
            .count()
        )
        if active_admins_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="O sistema precisa possuir pelo menos um administrador."
            )

    now = utc_now()
    # Finaliza qualquer sessão de trabalho ativa ou pausada
    db.query(WorkSession).filter(
        WorkSession.user_id == user.id,
        WorkSession.status.in_(["ACTIVE", "PAUSED"])
    ).update({"status": "FINISHED", "ended_at": now}, synchronize_session=False)

    # Desconecta integrações de música
    db.query(UserMusicConnection).filter(UserMusicConnection.user_id == user.id).update(
        {"is_connected": False, "is_playing": False, "access_token": None, "refresh_token": None, "updated_at": now},
        synchronize_session=False
    )

    # Soft-delete definitivo do usuário
    user.is_deleted = True
    user.active = False
    user.deleted_at = now

    db.commit()
    return {"message": f"Usuário '{user.name}' ({user.email}) removido com sucesso."}


