from __future__ import annotations

from app.models import Driver, Profile, User
from app.repositories.base import Repository


class UserRepository(Repository[User]):
    model = User

    def by_email(self, email: str) -> User | None:
        return self.db.query(User).filter(User.email == email.lower()).first()

    def create(self, email: str, password_hash: str | None, full_name: str, phone: str | None = None, **kw) -> User:
        user = User(email=email.lower(), password_hash=password_hash, **kw)
        user.profile = Profile(full_name=full_name, phone=phone)
        return self.add(user)

    def driver_for(self, user_id: int) -> Driver | None:
        return self.db.query(Driver).filter(Driver.user_id == user_id).first()
