"""
多房间管理器
管理所有监控房间的生命周期
"""
import threading
import time
from typing import Dict, Optional

import config
from services.data_service import DataService
from models.database import LiveRoom, get_china_now
from utils.logger import get_logger

logger = get_logger("room_manager")


class MonitoredRoom:
    """单个监控房间实例"""

    def __init__(self, live_id: str, db_session, manager, socketio=None):
        """
        初始化监控房间
        :param live_id: 直播间ID（作为唯一标识）
        :param db_session: 数据库会话
        :param manager: 房间管理器引用
        :param socketio: Socket.IO实例
        """
        self.live_id = live_id
        self.db = db_session
        self.manager = manager
        self.socketio = socketio

        self.fetcher = None  # WebDouyinLiveFetcher实例
        self.thread = None  # 监控线程
        self.shutdown_event = threading.Event()  # 关闭事件
        self.reconnect_count = 0  # 重连次数
        self.last_connect_time = None  # 最后连接时间

        # 本地统计缓存
        self.stats = {
            'current_user_count': 0,
            'total_user_count': 0,
            'total_income': 0,
            'contributor_count': 0
        }
        self.last_stats = {
            'current_user_count': 0,
            'total_user_count': 0
        }

        # 贡献榜和送礼用户缓存
        self.user_contributions = {}
        self.gift_users = set()
        self.combo_gifts = {}

        logger.info(f"创建监控房间实例: live_id={live_id}")

    def start(self):
        """启动监控（在新线程中）"""
        if self.thread and self.thread.is_alive():
            logger.warning(f"房间 {self.live_id} 的监控线程已在运行")
            return

        self.shutdown_event.clear()
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()
        logger.info(f"启动房间 {self.live_id} 的监控线程")

    def stop(self):
        """停止监控"""
        self.shutdown_event.set()
        if self.fetcher:
            try:
                self.fetcher.stop()
            except Exception as e:
                logger.error(f"停止fetcher时出错: {e}")

        # 更新数据库状态
        self.manager.data_service.update_live_room_status(
            self.live_id,
            'stopped',
            '用户手动停止'
        )
        self.manager.data_service.log_system_event(
            self.live_id,
            'disconnect',
            '用户手动停止监控',
            anchor_name=self.anchor_name if hasattr(self, 'anchor_name') else None
        )
        logger.info(f"房间 {self.live_id} 已停止监控")

    def _monitor_loop(self):
        """监控循环（支持自动重连）"""
        from ws_handlers.handlers import WebDouyinLiveFetcher

        while not self.shutdown_event.is_set():
            try:
                # 创建新的fetcher实例
                self.fetcher = WebDouyinLiveFetcher(
                    self.live_id,
                    self.manager.data_service,
                    self.socketio,
                    self
                )

                # 记录连接时间
                self.last_connect_time = get_china_now()
                self.manager.data_service.update_live_room(
                    self.live_id,
                    last_connect_time=self.last_connect_time
                )

                # 获取房间状态，只有在直播时才继续连接
                is_live = self.fetcher.get_room_status()

                if not is_live:
                    logger.warning(f"房间 {self.live_id} 当前未开播")
                    # 更新状态为等待
                    self.manager.data_service.update_live_room_status(
                        self.live_id,
                        'offline',
                        '主播未开播'
                    )
                    self.manager.data_service.log_system_event(
                        self.live_id,
                        'not_live',
                        '检测到主播未开播',
                        anchor_name=self.anchor_name if hasattr(self, 'anchor_name') else None
                    )

                    # 根据监控类型决定下一步操作
                    room = self.manager.data_service.get_live_room(self.live_id)
                    if room and room.monitor_type == '24h' and room.auto_reconnect:
                        # 24小时监控：进入轮询模式
                        logger.info(f"房间 {self.live_id} 为24小时监控，进入轮询模式")
                        if self._poll_room_status():
                            # 检测到开播，重置重连次数并继续
                            self.reconnect_count = 0
                            self.manager.data_service.update_live_room_reconnect(self.live_id, 0)
                            continue
                        else:
                            # 轮询超时或被中断
                            break
                    else:
                        # 手动监控：直接停止
                        logger.info(f"房间 {self.live_id} 为手动监控，停止监控")
                        self.manager.data_service.update_live_room_status(
                            self.live_id,
                            'stopped',
                            '主播未开播，停止监控'
                        )
                        break
                else:
                    # 更新状态为监控中
                    self.manager.data_service.update_live_room_status(
                        self.live_id,
                        'monitoring'
                    )
                    self.manager.data_service.log_system_event(
                        self.live_id,
                        'connect',
                        f'开始监控直播间 {self.live_id}',
                        anchor_name=self.anchor_name if hasattr(self, 'anchor_name') else None
                    )

                    # 启动WebSocket连接（阻塞直到断开）
                    self.fetcher.start()

            except Exception as e:
                logger.error(f"房间 {self.live_id} 监控出错: {e}")

                # 记录错误
                self.manager.data_service.update_live_room_status(
                    self.live_id,
                    'error',
                    str(e)
                )
                self.manager.data_service.log_system_event(
                    self.live_id,
                    'error',
                    f'监控出错: {str(e)}',
                    {'error': str(e)},
                    anchor_name=self.anchor_name if hasattr(self, 'anchor_name') else None
                )

            # 检查是否应该重连（仅在已连接的情况下）
            if self.shutdown_event.is_set():
                logger.info(f"房间 {self.live_id} 收到停止信号，退出监控循环")
                break

            # 只有在之前成功连接过的情况下才考虑重连
            # （避免在未开播时无限重试）
            if self.should_reconnect() and self.last_connect_time:
                self.reconnect_count += 1
                self.manager.data_service.update_live_room_reconnect(
                    self.live_id,
                    self.reconnect_count
                )
                self.manager.data_service.log_system_event(
                    self.live_id,
                    'reconnect',
                    f'准备第 {self.reconnect_count} 次重连',
                    anchor_name=self.anchor_name if hasattr(self, 'anchor_name') else None
                )
                logger.info(f"房间 {self.live_id} 准备第 {self.reconnect_count} 次重连")
                time.sleep(config.MONITOR_RECONNECT_DELAY)
            else:
                # 检查是否应该进入轮询模式（仅当开启自动重连时）
                room = self.manager.data_service.get_live_room(self.live_id)
                if room and room.auto_reconnect:
                    logger.info(f"房间 {self.live_id} 达到最大重连次数，进入等待开播状态")
                    self.manager.data_service.update_live_room_status(
                        self.live_id,
                        'waiting',
                        '等待主播开播'
                    )
                    self.manager.data_service.log_system_event(
                        self.live_id,
                        'waiting',
                        '达到最大重连次数，开始轮询直播状态',
                        anchor_name=self.anchor_name if hasattr(self, 'anchor_name') else None
                    )
                    # 进入轮询模式
                    if self._poll_room_status():
                        # 检测到开播，重置重连次数并继续循环
                        self.reconnect_count = 0
                        self.manager.data_service.update_live_room_reconnect(self.live_id, 0)
                        logger.info(f"房间 {self.live_id} 检测到开播，准备重新连接")
                        continue
                    else:
                        # 轮询被中断（shutdown_event被设置）
                        break
                else:
                    logger.info(f"房间 {self.live_id} 达到最大重连次数且未开启自动重连，退出监控循环")
                    self.manager.data_service.update_live_room_status(
                        self.live_id,
                        'stopped',
                        '达到最大重连次数'
                    )
                    break

    def _poll_room_status(self) -> bool:
        """
        轮询直播间状态，等待主播开播
        :return: True 表示检测到开播，False 表示被中断或应该停止
        """
        from crawler import DouyinLiveWebFetcher

        logger.info(f"房间 {self.live_id} 开始轮询直播状态")

        poll_count = 0
        max_poll_attempts = 10  # 最多轮询10次（10分钟），避免无限等待

        while not self.shutdown_event.is_set() and poll_count < max_poll_attempts:
            try:
                # 创建临时 fetcher 用于检测状态
                temp_fetcher = DouyinLiveWebFetcher(self.live_id)
                is_live = temp_fetcher.get_room_status()

                # get_room_status 返回 True 表示正在直播
                if is_live:
                    logger.info(f"房间 {self.live_id} 检测到正在直播，准备连接")
                    self.manager.data_service.log_system_event(
                        self.live_id,
                        'detected',
                        '检测到主播开播，准备重新连接',
                        anchor_name=self.anchor_name if hasattr(self, 'anchor_name') else None
                    )
                    return True
                else:
                    poll_count += 1
                    logger.debug(f"房间 {self.live_id} 未开播，继续等待... ({poll_count}/{max_poll_attempts})")

            except Exception as e:
                logger.debug(f"房间 {self.live_id} 轮询状态时出错: {e}")

            # 等待指定间隔后再次检测
            for _ in range(config.MONITOR_STATUS_POLL_INTERVAL):
                if self.shutdown_event.is_set():
                    return False
                time.sleep(1)

        # 达到最大轮询次数仍未检测到开播，停止监控
        logger.warning(f"房间 {self.live_id} 轮询超时（{max_poll_attempts}次），停止监控")
        self.manager.data_service.update_live_room_status(
            self.live_id,
            'stopped',
            '轮询超时，未检测到开播'
        )
        self.manager.data_service.log_system_event(
            self.live_id,
            'poll_timeout',
            f'轮询超时（{max_poll_attempts}次），停止监控',
            anchor_name=self.anchor_name if hasattr(self, 'anchor_name') else None
        )
        return False

    def should_reconnect(self) -> bool:
        """判断是否应该重连"""
        # 从数据库获取房间配置
        room = self.manager.data_service.get_live_room(self.live_id)
        if not room:
            return False

        if not room.auto_reconnect:
            return False

        if self.reconnect_count >= config.MONITOR_MAX_RETRIES:
            return False

        return True

    def get_stats(self) -> Dict:
        """获取统计信息"""
        return self.stats.copy()

    def update_contribution(self, user_id: str, user_name: str, gift_value: float = 0,
                           gift_count: int = 0, chat_count: int = 0, user_avatar: str = None):
        """更新用户贡献"""
        if user_id not in self.user_contributions:
            self.user_contributions[user_id] = {
                'user_name': user_name,
                'score': 0,
                'avatar': user_avatar,
                'gift_count': 0
            }
            logger.info(f"[新贡献用户] {user_id}={user_name}, avatar={user_avatar}, gift_value={gift_value}")
        else:
            old_name = self.user_contributions[user_id]['user_name']
            old_avatar = self.user_contributions[user_id].get('avatar')
            # 如果已有记录，更新用户名和头像（可能发生变化）
            self.user_contributions[user_id]['user_name'] = user_name
            if user_avatar:
                self.user_contributions[user_id]['avatar'] = user_avatar
            if old_name != user_name or old_avatar != user_avatar:
                logger.info(f"[更新用户信息] {user_id}: {old_name} -> {user_name}, avatar: {old_avatar} -> {user_avatar}")

        self.user_contributions[user_id]['score'] += gift_value
        self.user_contributions[user_id]['gift_count'] = self.user_contributions[user_id].get('gift_count', 0) + gift_count
        logger.info(f"[更新贡献] {user_id}={user_name}, score={self.user_contributions[user_id]['score']}, gift_count={self.user_contributions[user_id]['gift_count']}")

        # 同步到数据库
        self.manager.data_service.update_user_contribution(
            self.live_id,
            self.anchor_name if hasattr(self, 'anchor_name') else None,
            user_id,
            user_name,
            gift_value=gift_value,
            gift_count=1,
            user_avatar=user_avatar
        )

    def get_contribution_rank(self, limit: int = 100) -> list:
        """获取贡献排行榜（只显示送过礼物的用户）"""
        rank_list = sorted(
            [
                {
                    'user_id': k,
                    'user': v['user_name'],
                    'score': v['score'],
                    'avatar': v['avatar']
                }
                for k, v in self.user_contributions.items()
                if v['score'] > 0  # 只包含贡献值大于0的用户（送过礼物的）
            ],
            key=lambda x: x['score'],
            reverse=True
        )[:limit]

        for i, item in enumerate(rank_list):
            item['rank'] = i + 1

        # 记录贡献榜数据用于调试
        if rank_list:
            top_5 = [{'rank': r['rank'], 'user_id': r['user_id'], 'user': r['user'], 'score': r['score']} for r in rank_list[:5]]
            logger.info(f"[贡献榜TOP5] {top_5}")

        return rank_list


class RoomManager:
    """管理所有监控房间的生命周期"""

    def __init__(self, data_service: DataService, socketio=None):
        """
        初始化房间管理器
        :param data_service: 数据服务实例
        :param socketio: Socket.IO实例
        """
        self.data_service = data_service
        self.socketio = socketio
        self.active_rooms: Dict[str, MonitoredRoom] = {}  # live_id -> MonitoredRoom
        self.lock = threading.Lock()

        # 启动时清理状态不一致的房间
        self._cleanup_stale_statuses()

        logger.info("房间管理器初始化完成")

    def _cleanup_stale_statuses(self):
        """
        清理状态不一致的房间
        当应用被强制退出后，数据库中的状态可能仍为 monitoring
        需要重置这些房间的状态为 stopped
        """
        try:
            # 获取所有状态为 monitoring 的房间
            monitoring_rooms = self.data_service.list_live_rooms(status='monitoring')

            for room in monitoring_rooms:
                # 如果房间不在活跃列表中，说明实际没有在监控
                if room.live_id not in self.active_rooms:
                    logger.warning(f"房间 {room.live_id} 状态为 monitoring 但实际未监控，重置状态")
                    self.data_service.update_live_room_status(
                        room.live_id,
                        'stopped',
                        '应用重启后状态重置'
                    )
                    self.data_service.log_system_event(
                        room.live_id,
                        'status_reset',
                        '应用重启：检测到状态不一致，已重置为 stopped',
                        anchor_name=room.anchor_name
                    )
        except Exception as e:
            logger.error(f"清理状态失败: {e}")

    def add_room(self, live_id: str, monitor_type: str = 'manual', auto_reconnect: bool = False) -> Optional[str]:
        """
        添加监控房间
        :param live_id: 直播间ID
        :param monitor_type: 监控类型 (24h/manual)
        :param auto_reconnect: 是否自动重连
        :return: 直播间ID，失败返回None
        """
        with self.lock:
            # 检查是否已存在
            existing_room = self.data_service.get_live_room(live_id)
            if existing_room:
                if existing_room.live_id in self.active_rooms:
                    logger.warning(f"直播间 {live_id} 已在监控中")
                    return None
            else:
                # 创建新房间记录
                self.data_service.create_live_room(
                    live_id=live_id,
                    anchor_name=live_id,  # 初始使用 live_id 作为占位符，后续会更新
                    monitor_type=monitor_type,
                    auto_reconnect=auto_reconnect,
                    status='stopped'
                )

            # 创建MonitoredRoom实例
            monitored_room = MonitoredRoom(
                live_id=live_id,
                db_session=self.data_service.get_session(),
                manager=self,
                socketio=self.socketio
            )

            self.active_rooms[live_id] = monitored_room
            logger.info(f"添加监控房间: live_id={live_id}")
            return live_id

    def remove_room(self, live_id: str) -> bool:
        """
        移除监控房间
        :param live_id: 直播间ID
        :return: 是否成功
        """
        with self.lock:
            if live_id not in self.active_rooms:
                logger.warning(f"房间 {live_id} 不在活跃列表中")
                return False

            monitored_room = self.active_rooms[live_id]
            monitored_room.stop()
            del self.active_rooms[live_id]
            logger.info(f"移除监控房间: live_id={live_id}")
            return True

    def get_room(self, live_id: str) -> Optional[MonitoredRoom]:
        """获取监控房间实例"""
        return self.active_rooms.get(live_id)

    def get_room_by_live_id(self, live_id: str) -> Optional[MonitoredRoom]:
        """根据live_id获取监控房间实例"""
        return self.active_rooms.get(live_id)

    def start_room(self, live_id: str) -> bool:
        """
        启动房间监控
        :param live_id: 直播间ID
        :return: 是否成功
        """
        with self.lock:
            monitored_room = self.active_rooms.get(live_id)
            if not monitored_room:
                # 房间不在活跃列表中，检查数据库中是否存在
                room = self.data_service.get_live_room(live_id)
                if not room:
                    logger.warning(f"房间 {live_id} 在数据库中不存在")
                    return False

                # 如果数据库状态为 monitoring，先重置为 stopped
                if room.status == 'monitoring':
                    logger.info(f"房间 {live_id} 数据库状态为 monitoring，重置为 stopped")
                    self.data_service.update_live_room_status(
                        live_id,
                        'stopped',
                        '启动前重置状态'
                    )

                # 创建 MonitoredRoom 实例并添加到活跃列表
                monitored_room = MonitoredRoom(
                    live_id=live_id,
                    db_session=self.data_service.get_session(),
                    manager=self,
                    socketio=self.socketio
                )
                self.active_rooms[live_id] = monitored_room
                logger.info(f"重新创建监控房间实例: live_id={live_id}")

            monitored_room.start()
            return True

    def stop_room(self, live_id: str) -> bool:
        """
        停止房间监控
        :param live_id: 直播间ID
        :return: 是否成功
        """
        with self.lock:
            monitored_room = self.active_rooms.get(live_id)
            if not monitored_room:
                # 房间不在活跃列表中，但可能数据库状态为 monitoring
                # 检查并修复状态不一致
                room = self.data_service.get_live_room(live_id)
                if room and room.status == 'monitoring':
                    logger.warning(f"房间 {live_id} 不在活跃列表中但数据库状态为 monitoring，重置状态")
                    self.data_service.update_live_room_status(
                        live_id,
                        'stopped',
                        '状态不一致，已重置'
                    )
                    return True
                logger.warning(f"房间 {live_id} 不存在")
                return False

            monitored_room.stop()
            return True

    def restart_failed_rooms(self) -> int:
        """
        重启失败的房间
        :return: 重启的房间数量
        """
        restarted = 0
        with self.lock:
            rooms_to_restart = []

            for live_id, monitored_room in list(self.active_rooms.items()):
                # 检查是否需要重启
                room = self.data_service.get_live_room(live_id)
                if room and room.status in ('error', 'stopped') and room.auto_reconnect:
                    # 检查线程是否已停止
                    if not monitored_room.thread or not monitored_room.thread.is_alive():
                        rooms_to_restart.append(live_id)

            for live_id in rooms_to_restart:
                monitored_room = self.active_rooms.get(live_id)
                if monitored_room:
                    monitored_room.start()
                    restarted += 1
                    logger.info(f"重启失败的房间: live_id={live_id}")

        return restarted

    def get_all_rooms_status(self) -> list:
        """获取所有房间的状态"""
        with self.lock:
            status_list = []
            for live_id, monitored_room in self.active_rooms.items():
                room = self.data_service.get_live_room(live_id)
                if room:
                    status_list.append({
                        'live_id': room.live_id,
                        'anchor_name': room.anchor_name,
                        'status': room.status,
                        'monitor_type': room.monitor_type,
                        'auto_reconnect': room.auto_reconnect,
                        'reconnect_count': room.reconnect_count,
                        'is_active': monitored_room.thread and monitored_room.thread.is_alive(),
                        'stats': monitored_room.get_stats()
                    })
            return status_list

    def shutdown(self):
        """关闭所有房间"""
        with self.lock:
            for live_id, monitored_room in list(self.active_rooms.items()):
                try:
                    monitored_room.stop()
                except Exception as e:
                    logger.error(f"关闭房间 {live_id} 时出错: {e}")

            self.active_rooms.clear()
            logger.info("所有监控房间已关闭")
