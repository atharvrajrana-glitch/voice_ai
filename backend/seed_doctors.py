"""Seed doctors into the database from the docs file."""
import asyncio
import sys
import os

# Add backend and workspace to path
backend_dir = os.path.dirname(os.path.abspath(__file__))
workspace_root = os.path.dirname(backend_dir)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)
if workspace_root not in sys.path:
    sys.path.insert(0, workspace_root)

from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.models.doctor import Doctor
import app  # noqa: F401


DOCTORS = [
    {
        "name": "DR. RAJESH SHARMA",
        "department": "Cardiology",
        "specialization": "Cardiology",
        "phone": "+91-9876543210",
        "email": "rajesh.sharma@medclear.com",
    },
    {
        "name": "DR. PRIYA PATEL",
        "department": "Pediatrics",
        "specialization": "Pediatrics",
        "phone": "+91-9876543211",
        "email": "priya.patel@medclear.com",
    },
    {
        "name": "DR. AMIT VERMA",
        "department": "Orthopedics",
        "specialization": "Orthopedics",
        "phone": "+91-9876543212",
        "email": "amit.verma@medclear.com",
    },
    {
        "name": "DR. NEHA KAPOOR",
        "department": "Dermatology",
        "specialization": "Dermatology",
        "phone": "+91-9876543213",
        "email": "neha.kapoor@medclear.com",
    },
    {
        "name": "DR. ARJUN MEHTA",
        "department": "General Medicine",
        "specialization": "General Medicine",
        "phone": "+91-9876543214",
        "email": "arjun.mehta@medclear.com",
    },
    {
        "name": "DR. SIMRAN KAUR",
        "department": "ENT",
        "specialization": "ENT",
        "phone": "+91-9876543215",
        "email": "simran.kaur@medclear.com",
    },
]


async def seed_doctors():
    """Load doctors into the database."""
    async with AsyncSessionLocal() as session:
        # Check if doctors already exist
        result = await session.execute(select(Doctor))
        existing = result.scalars().all()
        
        if existing:
            print(f"✓ Database already has {len(existing)} doctors. Skipping seed.")
            return
        
        print("Loading doctors into database...")
        for doctor_data in DOCTORS:
            doctor = Doctor(**doctor_data)
            session.add(doctor)
        
        await session.commit()
        print(f"✓ Successfully seeded {len(DOCTORS)} doctors!")


if __name__ == "__main__":
    asyncio.run(seed_doctors())
