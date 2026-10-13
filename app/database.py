from sqlalchemy import create_engine, Column, Integer, String, DateTime, Float, Boolean
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import sessionmaker
import datetime
import sqlite3
import sys
from pathlib import Path

BASE_DIR = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parent
)
DATABASE_PATH = BASE_DIR / "recall.db"
DATABASE_URL = f"sqlite:///{DATABASE_PATH.as_posix()}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass

class Activity(Base):
    __tablename__ = "activities"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc), index=True)
    image_path = Column(String, index=True)
    app_name = Column(String, index=True)
    window_title = Column(String)
    url = Column(String, nullable=True)
    mouse_x = Column(Integer)
    mouse_y = Column(Integer)
    ram_percent = Column(Float, nullable=True)
    cpu_percent = Column(Float, nullable=True)
    upload_speed = Column(Float, nullable=True)
    download_speed = Column(Float, nullable=True)
    is_idle = Column(Boolean, default=False)
    top_background_apps = Column(String, nullable=True)

    icon_path = Column(String, nullable=True)
    interval_at_capture = Column(Integer, nullable=True)
    ocr_text = Column(String, nullable=True)

class AppTag(Base):
    __tablename__ = "app_tags"

    app_name = Column(String, primary_key=True, index=True)
    tag_name = Column(String, primary_key=True, index=True)

class Tag(Base):
    __tablename__ = "tags"

    name = Column(String, primary_key=True, index=True)

# Create tables if they don't exist
Base.metadata.create_all(bind=engine)

# Auto-migrate existing sqlite db
try:
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(activities)")
    columns = [col[1] for col in cursor.fetchall()]
    if "ram_percent" not in columns:
        cursor.execute("ALTER TABLE activities ADD COLUMN ram_percent REAL")
    if "upload_speed" not in columns:
        cursor.execute("ALTER TABLE activities ADD COLUMN upload_speed REAL")
    if "download_speed" not in columns:
        cursor.execute("ALTER TABLE activities ADD COLUMN download_speed REAL")
    if "icon_path" not in columns:
        cursor.execute("ALTER TABLE activities ADD COLUMN icon_path TEXT")
    if "interval_at_capture" not in columns:
        cursor.execute("ALTER TABLE activities ADD COLUMN interval_at_capture INTEGER")
    if "ocr_text" not in columns:
        cursor.execute("ALTER TABLE activities ADD COLUMN ocr_text TEXT")
    if "cpu_percent" not in columns:
        cursor.execute("ALTER TABLE activities ADD COLUMN cpu_percent REAL")
    if "is_idle" not in columns:
        cursor.execute("ALTER TABLE activities ADD COLUMN is_idle BOOLEAN DEFAULT 0")
    if "top_background_apps" not in columns:
        cursor.execute("ALTER TABLE activities ADD COLUMN top_background_apps TEXT")
    if "url" not in columns:
        cursor.execute("ALTER TABLE activities ADD COLUMN url TEXT")
    conn.commit()
    conn.close()
except Exception as e:
    print("Database migration error:", e)
