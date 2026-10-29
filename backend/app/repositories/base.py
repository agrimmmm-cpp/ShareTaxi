from __future__ import annotations

from typing import Generic, Sequence, TypeVar

from sqlalchemy.orm import Session

T = TypeVar("T")


class Repository(Generic[T]):
    model: type[T]

    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, id_: int) -> T | None:
        return self.db.get(self.model, id_)

    def add(self, obj: T) -> T:
        self.db.add(obj)
        self.db.flush()
        return obj

    def all(self, limit: int = 200) -> Sequence[T]:
        return self.db.query(self.model).limit(limit).all()
