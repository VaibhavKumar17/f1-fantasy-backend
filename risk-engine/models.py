from sqlalchemy import Column, Integer, String
from database import Base

class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String)
    driver1 = Column(String)
    driver2 = Column(String)
    driver3 = Column(String)
    driver4 = Column(String)
    driver5 = Column(String)
    constructor1 = Column(String, nullable=True)
    constructor2 = Column(String, nullable=True)


class TeamPick(Base):
    """Locked team per race round (for scoring after weekend)."""
    __tablename__ = "team_picks"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, index=True)
    race_round = Column(String, index=True)
    driver1 = Column(String)
    driver2 = Column(String)
    driver3 = Column(String)
    driver4 = Column(String)
    driver5 = Column(String)
    constructor1 = Column(String, nullable=True)
    constructor2 = Column(String, nullable=True)


class RaceScore(Base):
    """Stored leaderboard for a race after the weekend is closed."""
    __tablename__ = "race_scores"

    id = Column(Integer, primary_key=True, index=True)
    race_round = Column(String, index=True)
    race_name = Column(String)
    username = Column(String, index=True)
    points = Column(Integer)