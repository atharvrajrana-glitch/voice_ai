import uuid

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class PatientDoctor(Base):
    __tablename__ = "patient_doctors"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4
    )

    patient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False
    )

    doctor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("doctors.id", ondelete="CASCADE"),
        nullable=False
    )

    patient = relationship(
        "Patient",
        back_populates="doctor_relationships"
    )

    doctor = relationship(
        "Doctor",
        back_populates="patient_relationships"
    )

    __table_args__ = (
        UniqueConstraint(
            "patient_id",
            "doctor_id",
            name="uq_patient_doctor"
        ),
    )