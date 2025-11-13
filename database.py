import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, BigInteger, DateTime, Text, Float, Boolean, JSON, text
from sqlalchemy import ForeignKey, and_
from sqlalchemy.orm import relationship
from datetime import datetime, timedelta
import uuid
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
    manager_id = Column(Integer, ForeignKey('managers.id'), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    orders = relationship("Order", back_populates="user")
    quiz_answers = relationship("QuizAnswer", back_populates="user")
    notifications = relationship("Notification", back_populates="user")
    program_progress = relationship("ProgramProgress", back_populates="user")
    manager = relationship("Manager", back_populates="users")

class QuizAnswer(Base):
    __tablename__ = "quiz_answers"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), index=True)
    question_id = Column(String(100))
    answer = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="quiz_answers")

class Order(Base):
    __tablename__ = "orders"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), index=True)
    amount = Column(Float)
    payment_status = Column(String(50), default='new')  # new, pending, paid, refunded, failed
    payment_date = Column(DateTime, nullable=True)
    transaction_id = Column(String(100), nullable=True)
    delivery_address = Column(Text, nullable=True)
    delivery_status = Column(String(50), default='pending')  # pending, shipped, delivered
    tracking_code = Column(String(100), nullable=True)
    eta_date = Column(DateTime, nullable=True)
    courier_date = Column(DateTime, nullable=True)
    courier_time = Column(String(50), nullable=True)
    in_lab_date = Column(DateTime, nullable=True)
    results_date = Column(DateTime, nullable=True)
    report_link = Column(Text, nullable=True)
    consultation_status = Column(String(50), default='not_offered')  # not_offered, offered, booked, completed
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="orders")

class Notification(Base):
    __tablename__ = "notifications"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), index=True)
    type = Column(String(50))  # reminder, courier, program, results, etc.
    message = Column(Text)
    scheduled_for = Column(DateTime)
    sent = Column(Boolean, default=False)
    sent_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="notifications")

class ProgramProgress(Base):
    __tablename__ = "program_progress"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), index=True)
    day_number = Column(Integer)
    completed = Column(Boolean, default=False)
    skipped = Column(Boolean, default=False)
    completed_at = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="program_progress")

class Manager(Base):
    __tablename__ = "managers"
    
    id = Column(Integer, primary_key=True, index=True)
    tg_id = Column(BigInteger, unique=True, index=True)
    username = Column(String(100), nullable=True)
    first_name = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True)
    can_edit_content = Column(Boolean, default=False)
    permissions = Column(JSON, default=lambda: {"view_orders": True, "edit_orders": True})
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    users = relationship("User", back_populates="manager")

class ReferralLink(Base):
    __tablename__ = "referral_links"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100))
    source_code = Column(String(50), unique=True, index=True)
    scenario = Column(String(50))
    is_active = Column(Boolean, default=True)
    created_by = Column(Integer, ForeignKey('managers.id'))
    created_at = Column(DateTime, default=datetime.utcnow)

class ContentVersion(Base):
    __tablename__ = "content_versions"
    
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), index=True)
    text = Column(Text)
    buttons = Column(JSON)
    comment = Column(Text, nullable=True)
    version = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)
    created_by = Column(Integer, ForeignKey('managers.id'))
    created_at = Column(DateTime, default=datetime.utcnow)

# Database setup
engine = create_async_engine(config.DATABASE_URL, echo=True)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def create_tables():
    """Создает все таблицы в базе данных"""
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("✅ Все таблицы базы данных созданы")
    except Exception as e:
        logger.error(f"❌ Ошибка создания таблиц: {e}")
        raise

async def get_user_by_tg_id(tg_id: int):
    """Получает пользователя по Telegram ID"""
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
                    user.scenario = scenario
                    user.updated_at = datetime.utcnow()
                    await session.commit()
                    logger.info(f"✅ Обновлен пользователь: {first_name} (ID: {user.id})")
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
            logger.info(f"✅ Создан новый пользователь: {first_name} (ID: {user.id})")
            return user
            
    except Exception as e:
        logger.error(f"❌ Ошибка создания/обновления пользователя: {e}")
        return None

async def create_order(user_id: int, amount: float, payment_status: str = 'pending'):
    """Создает новый заказ"""
    try:
        async with AsyncSessionLocal() as session:
            order = Order(
                user_id=user_id,
                amount=amount,
                payment_status=payment_status
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
            logger.info(f"💾 Сохранен ответ: {question_id} = {answer} для пользователя {user_id}")
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
                order.updated_at = datetime.utcnow()
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
                user.updated_at = datetime.utcnow()
                await session.commit()
                logger.info(f"✅ Обновлен статус пользователя #{user_id}: {status}")
                return True
            return False
    except Exception as e:
        logger.error(f"❌ Ошибка обновления пользователя #{user_id}: {e}")
        return False

async def update_user_contact(user_id: int, phone: str, email: str = None):
    """Обновляет контактные данные пользователя"""
    try:
        async with AsyncSessionLocal() as session:
            user = await session.get(User, user_id)
            if user:
                user.phone = phone
                if email:
                    user.email = email
                user.updated_at = datetime.utcnow()
                await session.commit()
                logger.info(f"✅ Обновлены контакты пользователя #{user_id}")
                return True
            return False
    except Exception as e:
        logger.error(f"❌ Ошибка обновления контактов пользователя #{user_id}: {e}")
        return False

async def update_user_timezone(user_id: int, timezone: str, city: str = None, address: str = None):
    """Обновляет часовой пояс и адрес пользователя"""
    try:
        async with AsyncSessionLocal() as session:
            user = await session.get(User, user_id)
            if user:
                user.timezone = timezone
                if city:
                    user.city = city
                if address:
                    user.address = address
                user.updated_at = datetime.utcnow()
                await session.commit()
                logger.info(f"✅ Обновлен часовой пояс пользователя #{user_id}: {timezone}")
                return True
            return False
    except Exception as e:
        logger.error(f"❌ Ошибка обновления часового пояса пользователя #{user_id}: {e}")
        return False

async def get_user_orders(user_id: int, limit: int = 10):
    """Получает заказы пользователя"""
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

async def create_notification(user_id: int, notification_type: str, message: str, scheduled_for: datetime):
    """Создает уведомление"""
    try:
        async with AsyncSessionLocal() as session:
            notification = Notification(
                user_id=user_id,
                type=notification_type,
                message=message,
                scheduled_for=scheduled_for
            )
            session.add(notification)
            await session.commit()
            logger.info(f"🔔 Создано уведомление для пользователя {user_id}: {notification_type}")
            return notification
    except Exception as e:
        logger.error(f"❌ Ошибка создания уведомления: {e}")
        return None

async def get_pending_notifications():
    """Получает ожидающие отправки уведомления"""
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("""
                    SELECT n.*, u.tg_id, u.timezone 
                    FROM notifications n 
                    JOIN users u ON n.user_id = u.id 
                    WHERE n.sent = false AND n.scheduled_for <= NOW()
                """)
            )
            notifications_data = result.fetchall()
            return notifications_data
    except Exception as e:
        logger.error(f"❌ Ошибка получения ожидающих уведомлений: {e}")
        return []

async def mark_notification_sent(notification_id: int):
    """Отмечает уведомление как отправленное"""
    try:
        async with AsyncSessionLocal() as session:
            notification = await session.get(Notification, notification_id)
            if notification:
                notification.sent = True
                notification.sent_at = datetime.utcnow()
                await session.commit()
                return True
            return False
    except Exception as e:
        logger.error(f"❌ Ошибка отметки уведомления как отправленного: {e}")
        return False

async def start_program_for_user(user_id: int):
    """Запускает 14-дневную программу для пользователя"""
    try:
        async with AsyncSessionLocal() as session:
            # Проверяем, не запущена ли уже программа
            existing_progress = await session.execute(
                text("SELECT * FROM program_progress WHERE user_id = :user_id ORDER BY day_number DESC LIMIT 1"),
                {"user_id": user_id}
            )
            existing = existing_progress.fetchone()
            
            if existing and existing.day_number < 14:
                # Программа уже запущена, продолжаем
                logger.info(f"🌱 Программа уже запущена для пользователя {user_id}")
                return existing.day_number
            
            # Запускаем с дня 1
            progress = ProgramProgress(
                user_id=user_id,
                day_number=1,
                completed=False
            )
            session.add(progress)
            await session.commit()
            logger.info(f"🌱 Запущена 14-дневная программа для пользователя {user_id}")
            return 1
    except Exception as e:
        logger.error(f"❌ Ошибка запуска программы для пользователя {user_id}: {e}")
        return None

async def mark_program_day_completed(user_id: int, day_number: int):
    """Отмечает день программы как выполненный"""
    try:
        async with AsyncSessionLocal() as session:
            progress = await session.execute(
                text("""
                    SELECT * FROM program_progress 
                    WHERE user_id = :user_id AND day_number = :day_number
                """),
                {"user_id": user_id, "day_number": day_number}
            )
            progress_data = progress.fetchone()
            
            if progress_data:
                progress_obj = await session.get(ProgramProgress, progress_data.id)
                progress_obj.completed = True
                progress_obj.completed_at = datetime.utcnow()
                await session.commit()
                
                # Создаем запись для следующего дня, если он существует
                if day_number < 14:
                    next_day = ProgramProgress(
                        user_id=user_id,
                        day_number=day_number + 1,
                        completed=False
                    )
                    session.add(next_day)
                    await session.commit()
                
                logger.info(f"✅ День {day_number} программы выполнен пользователем {user_id}")
                return True
            return False
    except Exception as e:
        logger.error(f"❌ Ошибка отметки дня программы: {e}")
        return False

async def get_user_program_progress(user_id: int):
    """Получает прогресс программы пользователя"""
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("""
                    SELECT * FROM program_progress 
                    WHERE user_id = :user_id 
                    ORDER BY day_number
                """),
                {"user_id": user_id}
            )
            progress_data = result.fetchall()
            return [ProgramProgress(**dict(progress._mapping)) for progress in progress_data]
    except Exception as e:
        logger.error(f"❌ Ошибка получения прогресса программы пользователя {user_id}: {e}")
        return []

async def get_all_users(limit: int = 100, offset: int = 0):
    """Получает всех пользователей (для админки)"""
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("SELECT * FROM users ORDER BY created_at DESC LIMIT :limit OFFSET :offset"),
                {"limit": limit, "offset": offset}
            )
            users_data = result.fetchall()
            return [User(**dict(user._mapping)) for user in users_data]
    except Exception as e:
        logger.error(f"❌ Ошибка получения пользователей: {e}")
        return []

async def get_all_orders(limit: int = 100, offset: int = 0):
    """Получает все заказы (для админки)"""
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("""
                    SELECT o.*, u.first_name, u.username, u.phone 
                    FROM orders o 
                    JOIN users u ON o.user_id = u.id 
                    ORDER BY o.created_at DESC 
                    LIMIT :limit OFFSET :offset
                """),
                {"limit": limit, "offset": offset}
            )
            orders_data = result.fetchall()
            return orders_data
    except Exception as e:
        logger.error(f"❌ Ошибка получения заказов: {e}")
        return []

async def get_statistics():
    """Получает статистику бота"""
    try:
        async with AsyncSessionLocal() as session:
            # Общее количество пользователей
            users_count = await session.execute(text("SELECT COUNT(*) FROM users"))
            total_users = users_count.scalar()
            
            # Пользователи с оплатами
            paid_users = await session.execute(text("SELECT COUNT(DISTINCT user_id) FROM orders WHERE payment_status = 'paid'"))
            total_paid = paid_users.scalar()
            
            # Общее количество заказов
            orders_count = await session.execute(text("SELECT COUNT(*) FROM orders"))
            total_orders = orders_count.scalar()
            
            # Оплаченные заказы
            paid_orders = await session.execute(text("SELECT COUNT(*) FROM orders WHERE payment_status = 'paid'"))
            total_paid_orders = paid_orders.scalar()
            
            # Пользователи, прошедшие квиз
            quiz_users = await session.execute(text("SELECT COUNT(DISTINCT user_id) FROM quiz_answers"))
            total_quiz = quiz_users.scalar()
            
            # Пользователи в программе
            program_users = await session.execute(text("SELECT COUNT(DISTINCT user_id) FROM program_progress"))
            total_program = program_users.scalar()
            
            return {
                "total_users": total_users,
                "paid_users": total_paid,
                "total_orders": total_orders,
                "paid_orders": total_paid_orders,
                "quiz_users": total_quiz,
                "program_users": total_program,
                "conversion_rate": round((total_paid / total_users * 100), 2) if total_users > 0 else 0
            }
    except Exception as e:
        logger.error(f"❌ Ошибка получения статистики: {e}")
        return {}

async def cleanup_old_data(days: int = 30):
    """Очищает старые данные (для обслуживания)"""
    try:
        async with AsyncSessionLocal() as session:
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            # Удаляем старые отправленные уведомления
            await session.execute(
                text("DELETE FROM notifications WHERE sent = true AND sent_at < :cutoff_date"),
                {"cutoff_date": cutoff_date}
            )
            
            await session.commit()
            logger.info(f"🧹 Очищены старые данные старше {days} дней")
            return True
    except Exception as e:
        logger.error(f"❌ Ошибка очистки данных: {e}")
        return False
