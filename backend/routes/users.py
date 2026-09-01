from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.database.connection import get_db
from backend.database.models import User, Channel, CollectionEvent, WorkSession, WorkSessionEvent
from backend.schemas.auth import UserAdminCreate, UserAdminUpdate, UserResponse
from backend.security.auth import get_password_hash, get_current_admin_user

router = APIRouter(prefix="/users", tags=["Users (Admin Only)"])

@router.get("", response_model=List[UserResponse])
def list_users(
    db: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user)
):
    """Lista todos os usuários cadastrados no sistema (Exclusivo para ADMIN)."""
    users = db.query(User).order_by(User.id.asc()).all()
    return [UserResponse.model_validate(u) for u in users]

@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user_admin(
    user_data: UserAdminCreate,
    db: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user)
):
    """Criação de novos usuários da equipe com hash seguro (Exclusivo para ADMIN)."""
    email_clean = user_data.email.lower().strip()
    existing = db.query(User).filter(User.email == email_clean).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"O e-mail '{email_clean}' já está cadastrado no sistema."
        )

    role_clean = user_data.role.upper().strip() if user_data.role else "USER"
    if role_clean not in ("ADMIN", "USER"):
        role_clean = "USER"

    new_user = User(
        name=user_data.name.strip(),
        email=email_clean,
        password_hash=get_password_hash(user_data.password),
        role=role_clean,
        active=user_data.active
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
    """Edição de usuário, troca de nível (ADMIN/USER), ativação/desativação e redefinição de senha."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuário não encontrado."
        )

    if update_data.name is not None:
        user.name = update_data.name.strip()
    
    if update_data.email is not None:
        email_clean = update_data.email.lower().strip()
        if email_clean != user.email:
            existing = db.query(User).filter(User.email == email_clean).first()
            if existing:
                raise HTTPException(status_code=400, detail="Este e-mail já está sendo utilizado por outro usuário.")
            user.email = email_clean

    if update_data.role is not None:
        role_clean = update_data.role.upper().strip()
        if role_clean in ("ADMIN", "USER"):
            user.role = role_clean

    if update_data.active is not None:
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
    """Remove um usuário do sistema (Exclusivo para ADMIN)."""
    if user_id == admin_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Você não pode excluir sua própria conta de administrador."
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")

    # Reatribui canais coletados para o admin ativo para manter o histórico integro
    db.query(Channel).filter(Channel.first_collected_by_id == user.id).update(
        {"first_collected_by_id": admin_user.id}, synchronize_session=False
    )
    # Remove eventos e sessões atrelados ao usuário
    db.query(CollectionEvent).filter(CollectionEvent.user_id == user.id).delete(synchronize_session=False)
    db.query(WorkSessionEvent).filter(WorkSessionEvent.user_id == user.id).delete(synchronize_session=False)
    db.query(WorkSession).filter(WorkSession.user_id == user.id).delete(synchronize_session=False)

    db.delete(user)
    db.commit()
    return {"message": f"Usuário '{user.name}' ({user.email}) removido com sucesso."}

