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
    city = Column(String(100), nullable=True)
    timezone = Column(String(50), nullable=True)
    source = Column(String(100), nullable=True)
    scenario = Column(String(50), default='default')
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
    created_at = Column(DateTime, default=datetime.utcnow)

# Database setup
engine = create_async_engine(config.DATABASE_URL, echo=True)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def create_tables():
    """Создаем таблицы в базе данных"""
    try:
        async with engine.begin() as conn:
            # Удаляем существующие таблицы и создаем заново (для разработки)
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        logger.info("✅ Таблицы базы данных созданы заново")
    except Exception as e:
        logger.error(f"❌ Ошибка создания таблиц: {e}")
        raise

async def get_user_by_tg_id(tg_id: int):
    """Получаем пользователя по Telegram ID"""
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

async def get_or_create_user(tg_id: int, username: str, first_name: str, source: str = 'direct'):
    """Получаем или создаем пользователя"""
    try:
        async with AsyncSessionLocal() as session:
            # Пытаемся найти существующего пользователя
            existing_user = await get_user_by_tg_id(tg_id)
            
            if existing_user:
                # Обновляем данные существующего пользователя
                user = await session.get(User, existing_user.id)
                if user:
                    user.username = username
                    user.first_name = first_name
                    user.source = source
                    await session.commit()
                    logger.info(f"✅ Обновлен пользователь: {first_name} (ID: {user.id})")
                    return user
            
            # Создаем нового пользователя
            user = User(
                tg_id=tg_id,
                username=username,
                first_name=first_name,
                source=source,
                status='active'
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            logger.info(f"✅ Создан новый пользователь: {first_name} (ID: {user.id})")
            return user
            
    except Exception as e:
        logger.error(f"❌ Ошибка создания/обновления пользователя: {e}")
        return None

async def create_order(user_id: int, amount: float):
    """Создает заказ"""
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
            logger.info(f"💰 Создан заказ #{order.id} для пользователя {user_id}")
            return order
    except Exception as e:
        logger.error(f"❌ Ошибка создания заказа: {e}")
        return None

async def save_quiz_answer(user_id: int, question_id: str, answer: str):
    """Сохраняет ответ на вопрос квиза"""
    try:
        async with AsyncSessionLocal() as session:
            quiz_answer = QuizAnswer(
                user_id=user_id,
                question_id=question_id,
                answer=answer
            )
            session.add(quiz_answer)
            await session.commit()
            logger.info(f"💾 Сохранен ответ: {question_id} = {answer}")
            return True
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения ответа: {e}")
        return False

async def update_order_payment(order_id: int, status: str, transaction_id: str = None):
    """Обновляет статус оплаты заказа"""
    try:
        async with AsyncSessionLocal() as session:
            order = await session.get(Order, order_id)
            if order:
                order.payment_status = status
                order.payment_date = datetime.utcnow()
                if transaction_id:
                    order.transaction_id = transaction_id
                await session.commit()
                logger.info(f"✅ Обновлен заказ #{order_id}: статус {status}")
                return True
            return False
    except Exception as e:
        logger.error(f"❌ Ошибка обновления заказа #{order_id}: {e}")
        return False

async def update_user_status(user_id: int, status: str):
    """Обновляет статус пользователя"""
    try:
        async with AsyncSessionLocal() as session:
            user = await session.get(User, user_id)
            if user:
                user.status = status
                await session.commit()
                logger.info(f"✅ Обновлен статус пользователя #{user_id}: {status}")
                return True
            return False
    except Exception as e:
        logger.error(f"❌ Ошибка обновления пользователя #{user_id}: {e}")
        return False

async def update_user_contact(user_id: int, phone: str):
    """Обновляет контактные данные пользователя"""
    try:
        async with AsyncSessionLocal() as session:
            user = await session.get(User, user_id)
            if user:
                user.phone = phone
                await session.commit()
                logger.info(f"✅ Обновлен телефон пользователя #{user_id}")
                return True
            return False
    except Exception as e:
        logger.error(f"❌ Ошибка обновления телефона пользователя #{user_id}: {e}")
        return False

async def update_user_timezone(user_id: int, timezone: str, city: str = None):
    """Обновляет часовой пояс пользователя"""
    try:
        async with AsyncSessionLocal() as session:
            user = await session.get(User, user_id)
            if user:
                user.timezone = timezone
                if city:
                    user.city = city
                await session.commit()
                logger.info(f"✅ Обновлен часовой пояс пользователя #{user_id}: {timezone}")
                return True
            return False
    except Exception as e:
        logger.error(f"❌ Ошибка обновления часового пояса пользователя #{user_id}: {e}")
        return False

async def get_user_orders(user_id: int):
    """Получает заказы пользователя"""
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("SELECT * FROM orders WHERE user_id = :user_id ORDER BY created_at DESC"),
                {"user_id": user_id}
            )
            orders_data = result.fetchall()
            return [Order(**dict(order._mapping)) for order in orders_data]
    except Exception as e:
        logger.error(f"❌ Ошибка получения заказов пользователя {user_id}: {e}")
        return []

async def cleanup_duplicate_users():
    """Удаляет дублирующихся пользователей"""
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("""
                DELETE FROM users 
                WHERE id NOT IN (
                    SELECT MIN(id) 
                    FROM users 
                    GROUP BY tg_id
                )
            """))
            await session.commit()
            logger.info("✅ Дублирующиеся пользователи очищены")
            return True
    except Exception as e:
        logger.error(f"❌ Ошибка очистки дублирующихся пользователей: {e}")
        return False
