import os
import shutil
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Support custom DB path for Render persistent disk (/data) or custom env vars
db_path = os.environ.get("DATABASE_PATH")
if not db_path:
    if os.path.exists("/data"):
        db_path = "/data/f1fantasy.db"
    else:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        parent_dir = os.path.dirname(current_dir)
        db_path = os.path.join(parent_dir, "f1fantasy.db")
        db_local_path = os.path.join(current_dir, "f1fantasy.db")
        
        if os.path.exists(db_local_path) and not os.path.exists(db_path):
            try:
                shutil.copy2(db_local_path, db_path)
            except Exception:
                pass

DATABASE_URL = f"sqlite:///{db_path}"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()