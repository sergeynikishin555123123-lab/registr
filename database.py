import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, BigInteger, DateTime, Text, Float, Boolean, text
from datetime import datetime
from config import config

logger = logging.getLogger(__name__)

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
    address = Column(Text, nullable=True)
    timezone = Column(String(50), nullable=True)
    source = Column(String(100), nullable=True)
    scenario = Column(String(50), default='default')
    status = Column(String(50), default='lead')
    consent = Column(Boolean, default=False)
    manager_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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
    eta_date = Column(DateTime, nullable=True)
    courier_date = Column(DateTime, nullable=True)
    courier_time = Column(String(50), nullable=True)
    in_lab_date = Column(DateTime, nullable=True)
    results_date = Column(DateTime, nullable=True)
    report_link = Column(Text, nullable=True)
    consultation_status = Column(String(50), default='not_offered')
    created_at = Column(DateTime, default=datetime.utcnow)

class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    type = Column(String(50))
    scheduled_for = Column(DateTime)
    sent = Column(Boolean, default=False)
    sent_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class ProgramProgress(Base):
    __tablename__ = "program_progress"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    day_number = Column(Integer)
    completed = Column(Boolean, default=False)
    skipped = Column(Boolean, default=False)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Manager(Base):
    __tablename__ = "managers"
    id = Column(Integer, primary_key=True, index=True)
    tg_id = Column(BigInteger, unique=True, index=True)
    username = Column(String(100), nullable=True)
    first_name = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True)
    can_edit_content = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class ReferralLink(Base):
    __tablename__ = "referral_links"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100))
    source_code = Column(String(50), unique=True)
    scenario = Column(String(50))
    is_active = Column(Boolean, default=True)
    created_by = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)

# Database setup
engine = create_async_engine(config.DATABASE_URL, echo=True)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def create_tables():
    """Создает таблицы в базе данных"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("✅ Таблицы базы данных созданы")

async def get_user_by_tg_id(tg_id: int):
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("SELECT * FROM users WHERE tg_id = :tg_id"), {"tg_id": tg_id})
        user_data = result.fetchone()
        if user_data:
            return User(**dict(user_data._mapping))
        return None

async def get_or_create_user(tg_id: int, username: str, first_name: str, source: str = 'direct'):
    existing_user = await get_user_by_tg_id(tg_id)
    async with AsyncSessionLocal() as session:
        if existing_user:
            user = await session.get(User, existing_user.id)
            user.username = username
            user.first_name = first_name
            user.source = source
            await session.commit()
            return user
        else:
            user = User(tg_id=tg_id, username=username, first_name=first_name, source=source)
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

async def create_order(user_id: int, amount: float):
    async with AsyncSessionLocal() as session:
        order = Order(user_id=user_id, amount=amount)
        session.add(order)
        await session.commit()
        await session.refresh(order)
        return order

async def save_quiz_answer(user_id: int, question_id: str, answer: str):
    async with AsyncSessionLocal() as session:
        quiz_answer = QuizAnswer(user_id=user_id, question_id=question_id, answer=answer)
        session.add(quiz_answer)
        await session.commit()
        return True

async def update_order_payment(order_id: int, status: str, transaction_id: str = None):
    async with AsyncSessionLocal() as session:
        order = await session.get(Order, order_id)
        if order:
            order.payment_status = status
            order.payment_date = datetime.utcnow()
            if transaction_id:
                order.transaction_id = transaction_id
            await session.commit()
            return True
        return False

async def update_user_status(user_id: int, status: str):
    async with AsyncSessionLocal() as session:
        user = await session.get(User, user_id)
        if user:
            user.status = status
            await session.commit()
            return True
        return False

async def update_user_contact(user_id: int, phone: str):
    async with AsyncSessionLocal() as session:
        user = await session.get(User, user_id)
        if user:
            user.phone = phone
            await session.commit()
            return True
        return False

async def update_user_timezone(user_id: int, timezone: str, city: str = None):
    async with AsyncSessionLocal() as session:
        user = await session.get(User, user_id)
        if user:
            user.timezone = timezone
            if city:
                user.city = city
            await session.commit()
            return True
        return False

async def get_user_orders(user_id: int):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("SELECT * FROM orders WHERE user_id = :user_id ORDER BY created_at DESC"),
            {"user_id": user_id}
        )
        orders_data = result.fetchall()
        return [Order(**dict(order._mapping)) for order in orders_data]
