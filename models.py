import os
from sqlalchemy import Column, Integer, String, BigInteger, Boolean, DateTime, Text, JSON
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    tg_id = Column(BigInteger, unique=True, index=True)
    username = Column(String(100), nullable=True)
    first_name = Column(String(100), nullable=True)
    phone = Column(String(20), nullable=True)
    city = Column(String(100), nullable=True)
    timezone = Column(String(50), nullable=True)
    source = Column(String(100), nullable=True)
    scenario = Column(String(50), default='default')  # НОВОЕ: сценарий воронки
    status = Column(String(50), default='lead')
    created_at = Column(DateTime, default=datetime.utcnow)

class QuizAnswer(Base):
    __tablename__ = "quiz_answers"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    question_id = Column(String(100))
    answer = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

class ReferralLink(Base):
    __tablename__ = "referral_links"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True)  # название ссылки
    scenario = Column(String(50))  # сценарий воронки
    created_by = Column(Integer)  # ID админа
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
