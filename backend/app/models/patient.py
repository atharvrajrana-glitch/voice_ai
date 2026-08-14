import uuid

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4
    )

    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False
    )

    phone: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        unique=True,
        index=True
    )

    email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        unique=True
    )

    doctor_relationships = relationship(
        "PatientDoctor",
        back_populates="patient",
        cascade="all, delete-orphan"
    )

    appointments = relationship(
        "Appointment",
        back_populates="patient",
        cascade="all, delete-orphan"
    )

    sessions = relationship(
    "PatientSession",
    back_populates="patient",
    cascade="all, delete-orphan",
    )