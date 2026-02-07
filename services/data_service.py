"""
数据服务层
封装所有数据库操作
"""
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy import create_engine, and_, or_, func, text
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.exc import IntegrityError

import config
from models.database import Base, LiveRoom, ChatMessage, GiftMessage, RoomStats, UserContribution, SystemEvent, LiveSession, get_china_now, CHINA_TZ
from utils.logger import get_logger

logger = get_logger("data_service")


class DataService:
    """封装所有数据库操作"""

    def __init__(self, database_url: str = None):
        """
        初始化数据服务
        :param database_url: 数据库连接URL
        """
        self.database_url = database_url or config.DATABASE_URL
        self.engine = create_engine(
            self.database_url,
            echo=config.DEBUG,
            pool_pre_ping=True,
            pool_recycle=3600
        )
        self.SessionLocal = scoped_session(sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine
        ))

    def create_tables(self):
        """创建所有数据库表"""
        Base.metadata.create_all(bind=self.engine)

    def drop_tables(self):
        """删除所有数据库表"""
        Base.metadata.drop_all(bind=self.engine)

    def get_session(self):
        """获取数据库会话"""
        return self.SessionLocal()

    def close_session(self):
        """关闭所有会话"""
        self.SessionLocal.remove()

    # ==================== 直播间操作 ====================

    def create_live_room(self, live_id: str, **kwargs) -> LiveRoom:
        """
        创建直播间记录
        :param live_id: 直播间ID
        :param kwargs: 其他字段
        :return: LiveRoom对象
        """
        session = self.get_session()
        try:
            room = LiveRoom(live_id=live_id, **kwargs)
            session.add(room)
            session.commit()
            session.refresh(room)
            return room
        except IntegrityError:
            session.rollback()
            return self.get_live_room_by_live_id(live_id)
        finally:
            session.close()

    def get_live_room(self, live_id: str) -> Optional[LiveRoom]:
        """根据live_id获取直播间"""
        session = self.get_session()
        try:
            return session.query(LiveRoom).filter(LiveRoom.live_id == live_id).first()
        finally:
            session.close()

    def list_live_rooms(self, status: str = None) -> List[LiveRoom]:
        """
        获取直播间列表
        :param status: 过滤状态
        :return: LiveRoom列表
        """
        session = self.get_session()
        try:
            query = session.query(LiveRoom)
            if status:
                query = query.filter(LiveRoom.status == status)
            return query.order_by(LiveRoom.created_at.desc()).all()
        finally:
            session.close()

    def get_24h_monitor_rooms(self) -> List[LiveRoom]:
        """获取所有24小时监控的房间（现在默认所有房间都是24小时监控）"""
        session = self.get_session()
        try:
            # 获取所有房间，因为现在默认都是24小时监控
            return session.query(LiveRoom).filter(
                LiveRoom.auto_reconnect == True
            ).all()
        finally:
            session.close()

    def update_live_room(self, live_id: str, **kwargs) -> bool:
        """更新直播间信息"""
        session = self.get_session()
        try:
            room = session.query(LiveRoom).filter(LiveRoom.live_id == live_id).first()
            if room:
                for key, value in kwargs.items():
                    if hasattr(room, key):
                        setattr(room, key, value)
                room.updated_at = get_china_now()
                session.commit()
                return True
            return False
        finally:
            session.close()

    def update_live_room_status(self, live_id: str, status: str, error_message: str = None) -> bool:
        """更新直播间状态"""
        return self.update_live_room(
            live_id,
            status=status,
            error_message=error_message,
            updated_at=get_china_now()
        )

    def update_live_room_reconnect(self, live_id: str, reconnect_count: int) -> bool:
        """更新重连次数"""
        return self.update_live_room(
            live_id,
            reconnect_count=reconnect_count
        )

    def delete_live_room(self, live_id: str) -> bool:
        """删除直播间"""
        session = self.get_session()
        try:
            room = session.query(LiveRoom).filter(LiveRoom.live_id == live_id).first()
            if room:
                session.delete(room)
                session.commit()
                return True
            return False
        finally:
            session.close()

    def get_stats_summary(self) -> Dict[str, int]:
        """获取统计摘要"""
        session = self.get_session()
        try:
            total_rooms = session.query(func.count(LiveRoom.live_id)).scalar()
            monitoring_rooms = session.query(func.count(LiveRoom.live_id)).filter(LiveRoom.status == 'monitoring').scalar()
            h24_rooms = session.query(func.count(LiveRoom.live_id)).filter(LiveRoom.monitor_type == '24h').scalar()

            return {
                'total_rooms': total_rooms or 0,
                'monitoring_rooms': monitoring_rooms or 0,
                'h24_rooms': h24_rooms or 0,
                'stopped_rooms': (total_rooms or 0) - (monitoring_rooms or 0)
            }
        finally:
            session.close()

    # ==================== 消息操作 ====================

    def save_chat_message(self, live_id: str, live_session_id: int = None, anchor_name: str = None, **kwargs) -> Optional[ChatMessage]:
        """保存弹幕消息"""
        session = self.get_session()
        try:
            msg = ChatMessage(live_id=live_id, live_session_id=live_session_id, anchor_name=anchor_name, **kwargs)
            session.add(msg)
            session.commit()
            session.refresh(msg)
            return msg
        except Exception as e:
            session.rollback()
            print(f"保存弹幕消息失败: {e}")
            return None
        finally:
            session.close()

    def save_gift_message(self, live_id: str, live_session_id: int = None, anchor_name: str = None, trace_id: str = None, **kwargs) -> Optional[GiftMessage]:
        """保存礼物消息"""
        session = self.get_session()
        try:
            msg = GiftMessage(
                live_id=live_id,
                live_session_id=live_session_id,
                anchor_name=anchor_name,
                trace_id=trace_id,
                **kwargs
            )
            session.add(msg)
            session.commit()
            session.refresh(msg)
            return msg
        except Exception as e:
            session.rollback()
            print(f"保存礼物消息失败: {e}")
            return None
        finally:
            session.close()

    def update_gift_message(self, msg_id: int, **kwargs) -> bool:
        """更新礼物消息（用于连击礼物更新数量和总价值）"""
        session = self.get_session()
        try:
            msg = session.query(GiftMessage).filter(GiftMessage.id == msg_id).first()
            if msg:
                for key, value in kwargs.items():
                    if hasattr(msg, key):
                        setattr(msg, key, value)
                session.commit()
                return True
            return False
        except Exception as e:
            session.rollback()
            print(f"更新礼物消息失败: {e}")
            return False
        finally:
            session.close()

    def get_chat_messages(self, live_id: str, limit: int = 100, offset: int = 0) -> List[ChatMessage]:
        """获取弹幕消息"""
        session = self.get_session()
        try:
            return session.query(ChatMessage).filter(
                ChatMessage.live_id == live_id
            ).order_by(ChatMessage.created_at.desc()).offset(offset).limit(limit).all()
        finally:
            session.close()

    def get_gift_messages(self, live_id: str, limit: int = 100, offset: int = 0) -> List[GiftMessage]:
        """获取礼物消息"""
        session = self.get_session()
        try:
            return session.query(GiftMessage).filter(
                GiftMessage.live_id == live_id
            ).order_by(GiftMessage.created_at.desc()).offset(offset).limit(limit).all()
        finally:
            session.close()

    def get_message_counts(self, live_id: str) -> Dict[str, int]:
        """获取消息总数"""
        session = self.get_session()
        try:
            chat_count = session.query(func.count(ChatMessage.id)).filter(
                ChatMessage.live_id == live_id
            ).scalar() or 0
            gift_count = session.query(func.count(GiftMessage.id)).filter(
                GiftMessage.live_id == live_id
            ).scalar() or 0
            return {
                'chat_count': chat_count,
                'gift_count': gift_count,
                'total_count': chat_count + gift_count
            }
        finally:
            session.close()

    def get_all_messages(self, live_id: str, limit: int = 100, offset: int = 0) -> List[Dict]:
        """获取所有消息（弹幕和礼物混合）"""
        session = self.get_session()
        try:
            # 使用原生SQL查询合并两种消息，支持分页
            sql = text("""
                SELECT 'chat' as type, id, user_name, user_level, content as display_content,
                       NULL as gift_name, NULL as gift_count, NULL as total_value, created_at
                FROM chat_messages
                WHERE live_id = :live_id
                UNION ALL
                SELECT 'gift' as type, id, user_name, user_level,
                       CONCAT(user_name, ' 赠送了 ', gift_name, 'x', gift_count) as display_content,
                       gift_name, gift_count, total_value, created_at
                FROM gift_messages
                WHERE live_id = :live_id
                ORDER BY created_at DESC
                LIMIT :limit OFFSET :offset
            """)
            result = session.execute(sql, {'live_id': live_id, 'limit': limit, 'offset': offset})
            # SQLAlchemy 2.0 兼容方式转换 Row 为 Dict
            return [row._asdict() if hasattr(row, '_asdict') else dict(row._mapping) for row in result]
        finally:
            session.close()

    # ==================== 统计操作 ====================

    def save_room_stats(self, live_id: str, anchor_name: str = None, **kwargs) -> Optional[RoomStats]:
        """保存统计快照"""
        session = self.get_session()
        try:
            stats = RoomStats(live_id=live_id, anchor_name=anchor_name, **kwargs)
            session.add(stats)
            session.commit()
            session.refresh(stats)
            return stats
        except Exception as e:
            session.rollback()
            print(f"保存统计快照失败: {e}")
            return None
        finally:
            session.close()

    def get_latest_stats(self, live_id: str) -> Optional[RoomStats]:
        """获取最新统计"""
        session = self.get_session()
        try:
            return session.query(RoomStats).filter(
                RoomStats.live_id == live_id
            ).order_by(RoomStats.stats_at.desc()).first()
        finally:
            session.close()

    def get_room_stats_history(self, live_id: str, hours: int = 24) -> List[RoomStats]:
        """获取统计历史"""
        session = self.get_session()
        try:
            since = get_china_now() - timedelta(hours=hours)
            return session.query(RoomStats).filter(
                and_(
                    RoomStats.live_id == live_id,
                    RoomStats.stats_at >= since
                )
            ).order_by(RoomStats.stats_at.asc()).all()
        finally:
            session.close()

    # ==================== 贡献榜操作 ====================

    def update_user_contribution(self, live_id: str, anchor_name: str, user_id: str, user_name: str,
                                 gift_value: float = 0, gift_count: int = 0,
                                 chat_count: int = 0, user_avatar: str = None) -> UserContribution:
        """更新用户贡献"""
        session = self.get_session()
        try:
            contribution = session.query(UserContribution).filter(
                and_(
                    UserContribution.live_id == live_id,
                    UserContribution.user_id == user_id
                )
            ).first()

            if contribution:
                contribution.total_score += gift_value
                contribution.gift_count += gift_count
                contribution.chat_count += chat_count
                if user_avatar:
                    contribution.user_avatar = user_avatar
                contribution.user_name = user_name  # 更新用户名
                if anchor_name:
                    contribution.anchor_name = anchor_name  # 更新主播名
                contribution.updated_at = get_china_now()
            else:
                contribution = UserContribution(
                    live_id=live_id,
                    anchor_name=anchor_name,
                    user_id=user_id,
                    user_name=user_name,
                    total_score=gift_value,
                    gift_count=gift_count,
                    chat_count=chat_count,
                    user_avatar=user_avatar
                )
                session.add(contribution)

            session.commit()
            session.refresh(contribution)
            return contribution
        except Exception as e:
            session.rollback()
            print(f"更新用户贡献失败: {e}")
            return None
        finally:
            session.close()

    def get_top_contributors(self, live_id: str, limit: int = 100) -> List[UserContribution]:
        """获取贡献榜TOP N"""
        session = self.get_session()
        try:
            return session.query(UserContribution).filter(
                UserContribution.live_id == live_id
            ).order_by(UserContribution.total_score.desc()).limit(limit).all()
        finally:
            session.close()

    def get_contributors_by_date_range(self, live_id: str = None, start_date: str = None, end_date: str = None, page: int = 1, page_size: int = 20) -> Dict[str, Any]:
        """
        按日期范围获取贡献榜（从礼物消息中聚合）
        :param live_id: 房间ID，None 表示所有房间
        :param start_date: 开始日期 (YYYY-MM-DD)
        :param end_date: 结束日期 (YYYY-MM-DD)
        :param page: 页码（从1开始）
        :param page_size: 每页数量
        :return: {'contributors': [...], 'total': 总数, 'page': 当前页, 'page_size': 每页数量, 'total_pages': 总页数}
        """
        session = self.get_session()
        try:
            from sqlalchemy import func, literal_column
            from collections import namedtuple

            # 构建查询条件
            conditions = []

            if live_id:
                conditions.append(GiftMessage.live_id == live_id)

            if start_date:
                start_datetime = datetime.strptime(start_date, '%Y-%m-%d').replace(
                    hour=0, minute=0, second=0, microsecond=0,
                    tzinfo=CHINA_TZ
                )
                conditions.append(GiftMessage.created_at >= start_datetime)

            if end_date:
                end_datetime = datetime.strptime(end_date, '%Y-%m-%d').replace(
                    hour=23, minute=59, second=59, microsecond=999999,
                    tzinfo=CHINA_TZ
                )
                conditions.append(GiftMessage.created_at <= end_datetime)

            # 先获取总数（不分组）
            count_query = session.query(
                func.count(func.distinct(
                    func.concat(GiftMessage.live_id, '_', GiftMessage.user_id)
                ))
            )
            if conditions:
                count_query = count_query.filter(and_(*conditions))
            total = count_query.scalar() or 0

            # 计算分页
            total_pages = (total + page_size - 1) // page_size if total > 0 else 1
            offset = (page - 1) * page_size

            # 聚合查询：按用户统计礼物贡献
            # 创建一个命名元组来存储结果
            ContributorResult = namedtuple('ContributorResult', [
                'live_id', 'anchor_name', 'user_id', 'user_name',
                'contribution_value', 'gift_count', 'user_level'
            ])

            # 使用子查询获取聚合数据
            subquery = session.query(
                GiftMessage.live_id,
                GiftMessage.anchor_name,
                GiftMessage.user_id,
                GiftMessage.user_name,
                func.sum(GiftMessage.total_value).label('contribution_value'),
                func.count(GiftMessage.id).label('gift_count'),
                func.min(GiftMessage.user_level).label('user_level')
            )

            if conditions:
                subquery = subquery.filter(and_(*conditions))

            subquery = subquery.group_by(
                GiftMessage.live_id,
                GiftMessage.anchor_name,
                GiftMessage.user_id,
                GiftMessage.user_name
            ).order_by(func.sum(GiftMessage.total_value).desc())

            # 添加分页到子查询
            subquery = subquery.limit(page_size).offset(offset)

            # 执行查询
            results = subquery.all()

            # 转换为字典列表，并从 user_contributions 表获取头像
            contributors = []
            for row in results:
                # 从 user_contributions 表获取用户头像
                user_contrib = session.query(UserContribution).filter(
                    and_(
                        UserContribution.live_id == row.live_id,
                        UserContribution.user_id == row.user_id
                    )
                ).first()

                # 计算弹幕数
                chat_conditions = [ChatMessage.user_id == row.user_id]
                if live_id:
                    chat_conditions.append(ChatMessage.live_id == live_id)
                else:
                    chat_conditions.append(ChatMessage.live_id == row.live_id)
                if start_date:
                    chat_conditions.append(ChatMessage.created_at >= start_datetime)
                if end_date:
                    chat_conditions.append(ChatMessage.created_at <= end_datetime)

                chat_count = session.query(func.count(ChatMessage.id)).filter(
                    and_(*chat_conditions)
                ).scalar() or 0

                contributors.append({
                    'live_id': row.live_id,
                    'anchor_name': row.anchor_name,
                    'user_id': row.user_id,
                    'nickname': row.user_name,
                    'contribution_value': int(row.contribution_value),
                    'gift_count': int(row.gift_count),
                    'chat_count': chat_count,
                    'user_avatar': user_contrib.user_avatar if user_contrib else None,
                    'user_level': row.user_level
                })

            return {
                'contributors': contributors,
                'total': total,
                'page': page,
                'page_size': page_size,
                'total_pages': total_pages
            }
        finally:
            session.close()

    def get_room_date_range(self, live_id: str = None) -> Dict[str, Optional[str]]:
        """
        获取房间的直播数据日期范围（最早和最晚的直播日期）
        :param live_id: 房间ID，None 表示所有房间
        :return: {'min_date': 'YYYY-MM-DD', 'max_date': 'YYYY-MM-DD'}
        """
        session = self.get_session()
        try:
            conditions = []
            if live_id:
                conditions.append(LiveSession.live_id == live_id)
            else:
                # 查询所有有数据的房间
                conditions.append(LiveSession.live_id.isnot(None))

            # 查询最早的直播日期
            min_date_query = session.query(
                func.date(LiveSession.start_time)
            ).filter(
                and_(*conditions, LiveSession.start_time.isnot(None))
            ).order_by(LiveSession.start_time.asc()).limit(1).scalar()

            # 查询最晚的直播日期
            max_date_query = session.query(
                func.date(LiveSession.start_time)
            ).filter(
                and_(*conditions, LiveSession.start_time.isnot(None))
            ).order_by(LiveSession.start_time.desc()).limit(1).scalar()

            return {
                'min_date': min_date_query.strftime('%Y-%m-%d') if min_date_query else None,
                'max_date': max_date_query.strftime('%Y-%m-%d') if max_date_query else None
            }
        finally:
            session.close()

    def get_all_rooms_date_range(self) -> Dict[str, Optional[str]]:
        """获取所有房间中最早和最晚的直播日期"""
        return self.get_room_date_range(live_id=None)

    def get_user_contribution(self, live_id: str, user_id: str) -> Optional[UserContribution]:
        """获取用户贡献"""
        session = self.get_session()
        try:
            return session.query(UserContribution).filter(
                and_(
                    UserContribution.live_id == live_id,
                    UserContribution.user_id == user_id
                )
            ).first()
        finally:
            session.close()

    def get_session_contributors(self, live_id: str, session_id: int, limit: int = 100) -> List[Dict]:
        """获取指定直播场次的贡献榜（按礼物消息聚合）"""
        session = self.get_session()
        try:
            # 从礼物消息中聚合统计每个用户的贡献
            # 由于 GiftMessage 表没有 user_avatar 字段，如果不关联查询，头像将为空
            # 这里简化处理：先聚合礼物数据，再单独批量查询用户头像（比复杂的 join 更可控）

            from sqlalchemy import func

            # 1. 聚合礼物数据
            gift_stats = session.query(
                GiftMessage.user_id,
                func.max(GiftMessage.user_name).label('user_name'),
                func.max(GiftMessage.user_level).label('user_level'),
                func.sum(GiftMessage.total_value).label('total_score'),
                func.count(GiftMessage.id).label('gift_count')
            ).filter(
                and_(
                    GiftMessage.live_id == live_id,
                    GiftMessage.live_session_id == session_id
                )
            ).group_by(
                GiftMessage.user_id
            ).order_by(
                func.sum(GiftMessage.total_value).desc()
            ).limit(limit).all()

            if not gift_stats:
                return []

            # 2. 获取涉及到的用户ID
            user_ids = [row.user_id for row in gift_stats]

            # 3. 批量查询用户头像
            avatars = {}
            if user_ids:
                user_rows = session.query(UserContribution.user_id, UserContribution.user_avatar).filter(
                    and_(
                        UserContribution.live_id == live_id,
                        UserContribution.user_id.in_(user_ids)
                    )
                ).all()
                avatars = {r.user_id: r.user_avatar for r in user_rows}

            # 4. 组装结果
            contributors = []
            for row in gift_stats:
                contributors.append({
                    'user_id': row.user_id,
                    'nickname': row.user_name or '',
                    'contribution_value': float(row.total_score),
                    'gift_count': row.gift_count,
                    'user_level': row.user_level,
                    'user_avatar': avatars.get(row.user_id) # 使用查询到的头像
                })
            return contributors
        finally:
            session.close()

    def get_session_messages(self, session_id: int, message_type: str = 'chat', limit: int = 100, offset: int = 0) -> List[Dict]:
        """获取指定直播场次的弹幕或礼物消息"""
        session = self.get_session()
        try:
            if message_type == 'chat':
                messages = session.query(ChatMessage).filter(
                    ChatMessage.live_session_id == session_id
                ).order_by(ChatMessage.created_at.desc()).offset(offset).limit(limit).all()

                return [{
                    'id': msg.id,
                    'user_id': msg.user_id,
                    'nickname': msg.user_name,
                    'user_level': msg.user_level,
                    'content': msg.content,
                    'created_at': msg.created_at.isoformat() if msg.created_at else None
                } for msg in messages]

            elif message_type == 'gift':
                messages = session.query(GiftMessage).filter(
                    GiftMessage.live_session_id == session_id
                ).order_by(GiftMessage.created_at.desc()).offset(offset).limit(limit).all()

                return [{
                    'id': msg.id,
                    'user_id': msg.user_id,
                    'nickname': msg.user_name,
                    'user_level': msg.user_level,
                    'gift_name': msg.gift_name,
                    'gift_count': msg.gift_count,
                    'combo_count': msg.gift_count if msg.send_type == 'combo' else 1,
                    'diamond_count': msg.total_value,
                    'created_at': msg.created_at.isoformat() if msg.created_at else None
                } for msg in messages]

            return []
        finally:
            session.close()

    def get_session_message_counts(self, session_id: int) -> Dict[str, int]:
        """获取场次消息总数"""
        session = self.get_session()
        try:
            chat_count = session.query(func.count(ChatMessage.id)).filter(
                ChatMessage.live_session_id == session_id
            ).scalar() or 0
            gift_count = session.query(func.count(GiftMessage.id)).filter(
                GiftMessage.live_session_id == session_id
            ).scalar() or 0
            return {
                'chat_count': chat_count,
                'gift_count': gift_count
            }
        finally:
            session.close()

    # ==================== 事件日志 ====================

    def log_system_event(self, live_id: str, event_type: str, message: str = None, data: Dict = None, anchor_name: str = None) -> SystemEvent:
        """记录系统事件"""
        session = self.get_session()
        try:
            event = SystemEvent(
                live_id=live_id,
                anchor_name=anchor_name,
                event_type=event_type,
                event_message=message,
                event_data=data
            )
            session.add(event)
            session.commit()
            session.refresh(event)
            return event
        except Exception as e:
            session.rollback()
            print(f"记录系统事件失败: {e}")
            return None
        finally:
            session.close()

    def get_system_events(self, live_id: str = None, event_type: str = None, limit: int = 100) -> List[SystemEvent]:
        """获取系统事件"""
        session = self.get_session()
        try:
            query = session.query(SystemEvent)
            if live_id:
                query = query.filter(SystemEvent.live_id == live_id)
            if event_type:
                query = query.filter(SystemEvent.event_type == event_type)
            return query.order_by(SystemEvent.created_at.desc()).limit(limit).all()
        finally:
            session.close()

    # ==================== 数据清理 ====================

    def cleanup_old_data(self, retention_days: int = None) -> Dict[str, int]:
        """清理旧数据"""
        retention_days = retention_days or config.DATA_RETENTION_DAYS
        if retention_days == 0:
            return {'message': '数据保留设置为永久保留，不清理'}

        cutoff_date = get_china_now() - timedelta(days=retention_days)
        session = self.get_session()
        try:
            chat_deleted = session.query(ChatMessage).filter(
                ChatMessage.created_at < cutoff_date
            ).delete()
            gift_deleted = session.query(GiftMessage).filter(
                GiftMessage.created_at < cutoff_date
            ).delete()
            stats_deleted = session.query(RoomStats).filter(
                RoomStats.stats_at < cutoff_date
            ).delete()
            event_deleted = session.query(SystemEvent).filter(
                SystemEvent.created_at < cutoff_date
            ).delete()

            session.commit()
            return {
                'chat_messages_deleted': chat_deleted,
                'gift_messages_deleted': gift_deleted,
                'stats_deleted': stats_deleted,
                'events_deleted': event_deleted,
                'cutoff_date': cutoff_date.isoformat()
            }
        except Exception as e:
            session.rollback()
            print(f"清理旧数据失败: {e}")
            return {'error': str(e)}
        finally:
            session.close()

    # ==================== 直播场次操作 ====================

    def create_live_session(self, live_id: str, anchor_name: str = None, **kwargs) -> Optional[LiveSession]:
        """创建新的直播场次"""
        session = self.get_session()
        try:
            session_obj = LiveSession(live_id=live_id, anchor_name=anchor_name, **kwargs)
            session.add(session_obj)
            session.commit()
            session.refresh(session_obj)
            return session_obj
        except Exception as e:
            session.rollback()
            logger.error(f"创建直播场次失败: {e}")
            return None
        finally:
            session.close()

    def get_current_live_session(self, live_id: str) -> Optional[LiveSession]:
        """获取当前进行中的直播场次"""
        session = self.get_session()
        try:
            return session.query(LiveSession).filter(
                and_(
                    LiveSession.live_id == live_id,
                    LiveSession.status == 'live'
                )
            ).order_by(LiveSession.start_time.desc()).first()
        finally:
            session.close()

    def end_live_session(self, session_id: int, peak_viewer_count: int = None) -> bool:
        """结束直播场次"""
        session = self.get_session()
        try:
            session_obj = session.query(LiveSession).filter(LiveSession.id == session_id).first()
            if session_obj:
                session_obj.status = 'ended'
                session_obj.end_time = get_china_now()
                if peak_viewer_count is not None:
                    session_obj.peak_viewer_count = max(session_obj.peak_viewer_count or 0, peak_viewer_count)
                session_obj.updated_at = get_china_now()
                session.commit()
                return True
            return False
        except Exception as e:
            session.rollback()
            logger.error(f"结束直播场次失败: {e}")
            return False
        finally:
            session.close()

    def update_session_stats(self, session_id: int, **kwargs) -> bool:
        """更新直播场次统计"""
        session = self.get_session()
        try:
            session_obj = session.query(LiveSession).filter(LiveSession.id == session_id).first()
            if session_obj:
                for key, value in kwargs.items():
                    if hasattr(session_obj, key):
                        setattr(session_obj, key, value)
                session_obj.updated_at = get_china_now()
                session.commit()
                return True
            return False
        except Exception as e:
            session.rollback()
            logger.error(f"更新直播场次统计失败: {e}")
            return False
        finally:
            session.close()

    def increment_session_stats(self, session_id: int, income_delta: float = 0,
                               gift_count_delta: int = 0, chat_count_delta: int = 0) -> bool:
        """增量更新直播场次统计"""
        session = self.get_session()
        try:
            session_obj = session.query(LiveSession).filter(LiveSession.id == session_id).first()
            if session_obj:
                session_obj.total_income += income_delta
                session_obj.total_gift_count += gift_count_delta
                session_obj.total_chat_count += chat_count_delta
                session_obj.updated_at = get_china_now()
                session.commit()
                return True
            return False
        except Exception as e:
            session.rollback()
            logger.error(f"增量更新直播场次统计失败: {e}")
            return False
        finally:
            session.close()

    def get_live_sessions(self, live_id: str = None, status: str = None, limit: int = 100) -> List[LiveSession]:
        """获取直播场次列表"""
        session = self.get_session()
        try:
            query = session.query(LiveSession)
            if live_id:
                query = query.filter(LiveSession.live_id == live_id)
            if status:
                query = query.filter(LiveSession.status == status)
            return query.order_by(LiveSession.start_time.desc()).limit(limit).all()
        finally:
            session.close()

    def get_live_session_stats(self, session_id: int) -> Optional[Dict]:
        """获取直播场次统计详情"""
        session = self.get_session()
        try:
            session_obj = session.query(LiveSession).filter(LiveSession.id == session_id).first()
            if not session_obj:
                return None

            return {
                'id': session_obj.id,
                'live_id': session_obj.live_id,
                'anchor_name': session_obj.anchor_name,
                'start_time': session_obj.start_time.isoformat() if session_obj.start_time else None,
                'end_time': session_obj.end_time.isoformat() if session_obj.end_time else None,
                'status': session_obj.status,
                'total_income': session_obj.total_income,
                'total_gift_count': session_obj.total_gift_count,
                'total_chat_count': session_obj.total_chat_count,
                'peak_viewer_count': session_obj.peak_viewer_count
            }
        finally:
            session.close()

    def get_room_sessions_stats(self, live_id: str, start_date: str = None, end_date: str = None, limit: int = 100) -> List[Dict]:
        """获取房间的直播场次统计列表"""
        session = self.get_session()
        try:
            query = session.query(LiveSession).filter(LiveSession.live_id == live_id)

            if start_date:
                # 添加时间部分，确保包含整天
                start_dt = datetime.fromisoformat(start_date + 'T00:00:00')
                # 添加时区信息
                start_dt = start_dt.replace(tzinfo=CHINA_TZ)
                query = query.filter(LiveSession.start_time >= start_dt)

            if end_date:
                # 添加时间部分，确保包含整天
                end_dt = datetime.fromisoformat(end_date + 'T23:59:59')
                # 添加时区信息
                end_dt = end_dt.replace(tzinfo=CHINA_TZ)
                query = query.filter(LiveSession.start_time <= end_dt)

            sessions = query.order_by(LiveSession.start_time.desc()).limit(limit).all()

            result = []
            for s in sessions:
                result.append({
                    'id': s.id,
                    'live_id': s.live_id,
                    'anchor_name': s.anchor_name,
                    'start_time': s.start_time.isoformat() if s.start_time else None,
                    'end_time': s.end_time.isoformat() if s.end_time else None,
                    'status': s.status,
                    'total_income': s.total_income,
                    'total_gift_count': s.total_gift_count,
                    'total_chat_count': s.total_chat_count,
                    'peak_viewer_count': s.peak_viewer_count
                })
            return result
        finally:
            session.close()

    def get_sessions_aggregated_stats(self, live_id: str = None, start_date: str = None, end_date: str = None) -> Dict:
        """获取按时间段聚合的直播统计数据"""
        session = self.get_session()
        try:
            query = session.query(LiveSession)

            if live_id:
                query = query.filter(LiveSession.live_id == live_id)

            if start_date:
                # 添加时间部分，确保包含整天
                start_dt = datetime.fromisoformat(start_date + 'T00:00:00')
                # 添加时区信息
                start_dt = start_dt.replace(tzinfo=CHINA_TZ)
                query = query.filter(LiveSession.start_time >= start_dt)

            if end_date:
                # 添加时间部分，确保包含整天
                end_dt = datetime.fromisoformat(end_date + 'T23:59:59')
                # 添加时区信息
                end_dt = end_dt.replace(tzinfo=CHINA_TZ)
                query = query.filter(LiveSession.start_time <= end_dt)

            sessions = query.all()

            total_income = sum(s.total_income or 0 for s in sessions)
            total_gift_count = sum(s.total_gift_count or 0 for s in sessions)
            total_chat_count = sum(s.total_chat_count or 0 for s in sessions)
            total_sessions = len(sessions)
            live_sessions = sum(1 for s in sessions if s.status == 'live')
            ended_sessions = sum(1 for s in sessions if s.status == 'ended')
            peak_viewer_max = max((s.peak_viewer_count or 0) for s in sessions) if sessions else 0

            # 计算总时长
            total_duration_seconds = 0
            for s in sessions:
                if s.start_time:
                    # 确保 start_time 和 end_time 都是带时区的
                    start = s.start_time
                    if start.tzinfo is None:
                        start = start.replace(tzinfo=CHINA_TZ)

                    end = s.end_time if s.end_time else get_china_now()
                    if end.tzinfo is None:
                        end = end.replace(tzinfo=CHINA_TZ)

                    total_duration_seconds += (end - start).total_seconds()

            avg_duration = total_duration_seconds / total_sessions if total_sessions > 0 else 0

            return {
                'total_sessions': total_sessions,
                'live_sessions': live_sessions,
                'ended_sessions': ended_sessions,
                'total_income': total_income,
                'total_gift_count': total_gift_count,
                'total_chat_count': total_chat_count,
                'peak_viewer_max': peak_viewer_max,
                'total_duration_seconds': total_duration_seconds,
                'avg_duration_seconds': avg_duration
            }
        finally:
            session.close()

    def cleanup_stale_live_sessions(self, stale_threshold_hours: int = 24) -> int:
        """
        清理长时间处于 'live' 状态但实际已结束的场次
        :param stale_threshold_hours: 超过多少小时的 'live' 场次被认为已结束，默认24小时
        :return: 清理的场次数量
        """
        from models.database import get_china_now
        from datetime import timedelta

        session = self.get_session()
        try:
            # 计算阈值时间
            threshold_time = get_china_now() - timedelta(hours=stale_threshold_hours)

            # 查找所有超过阈值时间且状态仍为 'live' 的场次
            stale_sessions = session.query(LiveSession).filter(
                and_(
                    LiveSession.status == 'live',
                    LiveSession.start_time < threshold_time
                )
            ).all()

            count = 0
            for stale_session in stale_sessions:
                stale_session.status = 'ended'
                stale_session.end_time = stale_session.start_time + timedelta(hours=2)  # 假设直播2小时后结束
                stale_session.updated_at = get_china_now()
                count += 1
                logger.info(f"清理未结束的直播场次: id={stale_session.id}, live_id={stale_session.live_id}, start_time={stale_session.start_time}")

            session.commit()
            return count
        except Exception as e:
            session.rollback()
            logger.error(f"清理未结束场次失败: {e}")
            return 0
        finally:
            session.close()
