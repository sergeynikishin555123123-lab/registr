import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, BigInteger, DateTime, Text, Float, Boolean, JSON, text
from sqlalchemy import ForeignKey
from datetime import datetime, timedelta
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
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Notification(Base):
    __tablename__ = "notifications"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    type = Column(String(50))
    message = Column(Text)
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

# Database setup - УПРОЩЕННАЯ версия
try:
    engine = create_async_engine(config.DATABASE_URL, echo=True)
    AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
except Exception as e:
    logger.error(f"❌ Ошибка подключения к БД: {e}")
    engine = None
    AsyncSessionLocal = None

async def create_tables():
    """Создает таблицы в базе данных"""
    if not engine:
        logger.error("❌ Двигатель БД не инициализирован")
        return
        
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("✅ Таблицы базы данных созданы")
    except Exception as e:
        logger.error(f"❌ Ошибка создания таблиц: {e}")

async def get_user_by_tg_id(tg_id: int):
    """Получает пользователя по Telegram ID"""
    if not AsyncSessionLocal:
        return None
        
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("SELECT * FROM users WHERE tg_id = :tg_id"),
                {"tg_id": tg_id}
            )
            user_data = result.fetchone()
            if user_data:
                return User(**dict(user_data._mapping))
            return None
    except Exception as e:
        logger.error(f"❌ Ошибка получения пользователя {tg_id}: {e}")
        return None

async def get_or_create_user(tg_id: int, username: str, first_name: str, source: str = 'direct', scenario: str = 'default'):
    """Получает или создает пользователя"""
    if not AsyncSessionLocal:
        return None
        
    try:
        # Сначала пытаемся найти существующего пользователя
        existing_user = await get_user_by_tg_id(tg_id)
        
        async with AsyncSessionLocal() as session:
            if existing_user:
                # Обновляем данные существующего пользователя
                user = await session.get(User, existing_user.id)
                if user:
                    user.username = username
                    user.first_name = first_name
                    user.source = source
                    user.scenario = scenario
                    user.updated_at = datetime.utcnow()
                    await session.commit()
                    logger.info(f"✅ Обновлен пользователь: {first_name}")
                    return user
            
            # Создаем нового пользователя
            user = User(
                tg_id=tg_id,
                username=username,
                first_name=first_name,
                source=source,
                scenario=scenario,
                status='active'
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            logger.info(f"✅ Создан новый пользователь: {first_name}")
            return user
            
    except Exception as e:
        logger.error(f"❌ Ошибка создания/обновления пользователя: {e}")
        return None

async def create_order(user_id: int, amount: float):
    """Создает новый заказ"""
    if not AsyncSessionLocal:
        return None
        
    try:
        async with AsyncSessionLocal() as session:
            order = Order(
                user_id=user_id,
                amount=amount,
                payment_status='pending'
            )
            session.add(order)
            await session.commit()
            await session.refresh(order)
            logger.info(f"💰 Создан заказ #{order.id}")
            return order
    except Exception as e:
        logger.error(f"❌ Ошибка создания заказа: {e}")
        return None

async def save_quiz_answer(user_id: int, question_id: str, answer: str):
    """Сохраняет ответ на вопрос квиза"""
    if not AsyncSessionLocal:
        return False
        
    try:
        async with AsyncSessionLocal() as session:
            quiz_answer = QuizAnswer(
                user_id=user_id,
                question_id=question_id,
                answer=answer
            )
            session.add(quiz_answer)
            await session.commit()
            logger.info(f"💾 Сохранен ответ: {question_id}")
            return True
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения ответа: {e}")
        return False

async def update_order_payment(order_id: int, status: str, transaction_id: str = None):
    """Обновляет статус оплаты заказа"""
    if not AsyncSessionLocal:
        return False
        
    try:
        async with AsyncSessionLocal() as session:
            order = await session.get(Order, order_id)
            if order:
                order.payment_status = status
                order.payment_date = datetime.utcnow()
                if transaction_id:
                    order.transaction_id = transaction_id
                order.updated_at = datetime.utcnow()
                await session.commit()
                logger.info(f"✅ Обновлен заказ #{order_id}")
                return True
            return False
    except Exception as e:
        logger.error(f"❌ Ошибка обновления заказа #{order_id}: {e}")
        return False

async def update_user_status(user_id: int, status: str):
    """Обновляет статус пользователя"""
    if not AsyncSessionLocal:
        return False
        
    try:
        async with AsyncSessionLocal() as session:
            user = await session.get(User, user_id)
            if user:
                user.status = status
                user.updated_at = datetime.utcnow()
                await session.commit()
                logger.info(f"✅ Обновлен статус пользователя #{user_id}")
                return True
            return False
    except Exception as e:
        logger.error(f"❌ Ошибка обновления пользователя #{user_id}: {e}")
        return False

async def update_user_contact(user_id: int, phone: str):
    """Обновляет контактные данные пользователя"""
    if not AsyncSessionLocal:
        return False
        
    try:
        async with AsyncSessionLocal() as session:
            user = await session.get(User, user_id)
            if user:
                user.phone = phone
                user.updated_at = datetime.utcnow()
                await session.commit()
                logger.info(f"✅ Обновлены контакты пользователя #{user_id}")
                return True
            return False
    except Exception as e:
        logger.error(f"❌ Ошибка обновления контактов пользователя #{user_id}: {e}")
        return False

async def update_user_timezone(user_id: int, timezone: str, city: str = None):
    """Обновляет часовой пояс пользователя"""
    if not AsyncSessionLocal:
        return False
        
    try:
        async with AsyncSessionLocal() as session:
            user = await session.get(User, user_id)
            if user:
                user.timezone = timezone
                if city:
                    user.city = city
                user.updated_at = datetime.utcnow()
                await session.commit()
                logger.info(f"✅ Обновлен часовой пояс пользователя #{user_id}")
                return True
            return False
    except Exception as e:
        logger.error(f"❌ Ошибка обновления часового пояса пользователя #{user_id}: {e}")
        return False

async def update_user_address(user_id: int, address: str):
    """Обновляет адрес пользователя"""
    if not AsyncSessionLocal:
        return False
        
    try:
        async with AsyncSessionLocal() as session:
            user = await session.get(User, user_id)
            if user:
                user.address = address
                user.updated_at = datetime.utcnow()
                await session.commit()
                logger.info(f"✅ Обновлен адрес пользователя #{user_id}")
                return True
            return False
    except Exception as e:
        logger.error(f"❌ Ошибка обновления адреса пользователя #{user_id}: {e}")
        return False

async def get_user_orders(user_id: int, limit: int = 5):
    """Получает заказы пользователя"""
    if not AsyncSessionLocal:
        return []
        
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("SELECT * FROM orders WHERE user_id = :user_id ORDER BY created_at DESC LIMIT :limit"),
                {"user_id": user_id, "limit": limit}
            )
            orders_data = result.fetchall()
            return [Order(**dict(order._mapping)) for order in orders_data]
    except Exception as e:
        logger.error(f"❌ Ошибка получения заказов пользователя {user_id}: {e}")
        return []

async def get_user_quiz_answers(user_id: int):
    """Получает ответы на квиз пользователя"""
    if not AsyncSessionLocal:
        return []
        
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("SELECT * FROM quiz_answers WHERE user_id = :user_id ORDER BY created_at"),
                {"user_id": user_id}
            )
            answers_data = result.fetchall()
            return [QuizAnswer(**dict(answer._mapping)) for answer in answers_data]
    except Exception as e:
        logger.error(f"❌ Ошибка получения ответов квиза пользователя {user_id}: {e}")
        return []
