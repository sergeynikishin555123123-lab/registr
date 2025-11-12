from sqlalchemy import Column, Integer, String, BigInteger, Boolean, DateTime, Text, Float
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
    email = Column(String(100), nullable=True)
    city = Column(String(100), nullable=True)
    timezone = Column(String(50), nullable=True)
    source = Column(String(100), nullable=True)
    consent = Column(Boolean, default=False)
    status = Column(String(50), default='lead')
    created_at = Column(DateTime, default=datetime.utcnow)

class QuizAnswer(Base):
    __tablename__ = "quiz_answers"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    question_id = Column(String(100))
    answer = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

class Order(Base):
    __tablename__ = "orders"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    amount = Column(Float)
    payment_status = Column(String(50), default='new')
    payment_date = Column(DateTime, nullable=True)
    transaction_id = Column(String(100), nullable=True)
    delivery_address = Column(Text, nullable=True)
    delivery_status = Column(String(50), default='pending')
    tracking_code = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
