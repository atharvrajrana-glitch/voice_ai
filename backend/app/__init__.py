"""App module."""

# Import all models to register them with SQLAlchemy
# CRITICAL: PatientDoctor must be imported BEFORE Patient so the relationship can resolve
from app.models.patient_doctor import PatientDoctor  # noqa: F401
from app.models.patient import Patient  # noqa: F401
from app.models.doctor import Doctor  # noqa: F401\
from app.models.lab_report import LabReport
from app.models.appointment import Appointment  # noqa: F401
from app.models.hospital_contact import HospitalContact  # noqa: F401
from app.models.patient_session import PatientSession  # noqa: F401

__all__ = [
    "Patient",
    "Doctor",
    "PatientDoctor",
    "Appointment",
    "HospitalContact",
    "PatientSession",
]
