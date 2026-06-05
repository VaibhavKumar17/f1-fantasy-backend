import os
import shutil
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Move DB file to parent directory so Uvicorn's file watcher doesn't trigger reload loops on read/write transactions
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
db_parent_path = os.path.join(parent_dir, "f1fantasy.db")
db_local_path = os.path.join(current_dir, "f1fantasy.db")

if os.path.exists(db_local_path) and not os.path.exists(db_parent_path):
    try:
        shutil.copy2(db_local_path, db_parent_path)
    except Exception:
        pass

DATABASE_URL = f"sqlite:///{db_parent_path}"

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(bind=engine)

Base = declarative_base()