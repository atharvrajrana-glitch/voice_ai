import os 
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, configure_mappers
from app.core.config import settings
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.environ.get("DATABASE_URL")

class Base(DeclarativeBase):
    pass

# Import app package to register all models via app.__init__.py
import app  # noqa: F401

# Explicitly configure mappers after all models are imported
configure_mappers()

DATABASE_URL 
engine = create_async_engine(
    DATABASE_URL, 
    pool_size=10, 
    max_overflow=20, 
    pool_recycle=1800
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session