"""
WebSocket处理器
扩展核心抓取类，添加数据库存储和Socket.IO推送
"""
import gzip
from typing import TYPE_CHECKING

import websocket

if TYPE_CHECKING:
    from services.room_manager import MonitoredRoom

from protobuf.douyin import PushFrame, Response, ChatMessage, GiftMessage, RoomUserSeqMessage, ControlMessage
from utils.logger import get_logger
import config


def parse_formatted_number(value):
    """
    解析抖音返回的格式化数字（如 '46.8万', '1.2亿'）转换为整数
    """
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)

    value_str = str(value).strip()
    if not value_str:
        return 0

    # 处理带"万"的数字
    if '万' in value_str:
        num_str = value_str.replace('万', '').strip()
        try:
            return int(float(num_str) * 10000)
        except ValueError:
            return 0

    # 处理带"亿"的数字
    if '亿' in value_str:
        num_str = value_str.replace('亿', '').strip()
        try:
            return int(float(num_str) * 100000000)
        except ValueError:
            return 0

    # 直接解析数字
    try:
        return int(value_str)
    except ValueError:
        return 0


class WebDouyinLiveFetcher:
    """
    扩展核心抓取类，添加数据库存储和Socket.IO推送
    保持与原有WebDouyinLiveFetcher的兼容性
    """

    def __init__(self, live_id: str, room_id: int, db_session, socketio_instance, monitored_room: 'MonitoredRoom',
                 proxy_enabled=None, proxy_url=None):
        """
        初始化
        :param live_id: 直播间ID
        :param room_id: 数据库房间ID
        :param db_session: 数据库会话
        :param socketio_instance: Socket.IO实例
        :param monitored_room: MonitoredRoom实例
        :param proxy_enabled: 是否启用代理（None则从配置文件读取）
        :param proxy_url: 代理URL（None则从配置文件读取）
        """
        from crawler import DouyinLiveWebFetcher

        self.live_id = live_id
        self.room_id = room_id
        self.db = db_session
        self.monitored_room = monitored_room
        self.socketio = socketio_instance

        # 代理配置
        self.proxy_enabled = proxy_enabled if proxy_enabled is not None else config.PROXY_ENABLED
        self.proxy_url = proxy_url if proxy_url is not None else config.get_proxy_url()

        # 初始化房间级日志器
        self.log = get_logger("handlers", live_id)

        # 创建核心抓取器实例，传递代理配置
        self._fetcher = DouyinLiveWebFetcher(live_id, proxy_enabled=self.proxy_enabled, proxy_url=self.proxy_url)

        # 设置回调函数
        self._fetcher._wsOnMessage = self._wsOnMessage
        self._fetcher._wsOnOpen = self._wsOnOpen
        self._fetcher._wsOnError = self._wsOnError
        self._fetcher._wsOnClose = self._wsOnClose

        # 本地数据（用于实时推送）
        self.traceId_list = []
        self.gift_users = set()
        self.total_income = 0
        self.current_session_id = None  # 当前直播场次ID
        self.current_viewer_count = 0  # 当前观看人数（用于计算峰值）
        self.max_viewer_count = 0  # 峰值观看人数

        self.log.info(f"初始化WebDouyinLiveFetcher: room_id={room_id}")

        # 尝试预加载当前场次数据（在所有实例变量初始化后）
        self._preload_session_data()

    def _preload_session_data(self):
        """预加载当前场次数据"""
        try:
            data_service = self.monitored_room.manager.data_service
            current_session = data_service.get_current_live_session(self.room_id)

            if current_session:
                self.current_session_id = current_session.id
                self.log.info(f"预加载现有直播场次: session_id={self.current_session_id}")

                # 加载贡献榜
                if not self.monitored_room.user_contributions:
                    session_contributors = data_service.get_session_contributors(self.room_id, current_session.id, limit=1000)
                    for contributor in session_contributors:
                        self.monitored_room.user_contributions[contributor['user_id']] = {
                            'user_name': contributor['user_name'],
                            'score': contributor['total_score'],
                            'avatar': contributor['user_avatar'],
                            'gift_count': contributor['gift_count']
                        }
                    self.log.info(f"预加载了 {len(session_contributors)} 个贡献者到本地缓存")
        except Exception as e:
            self.log.error(f"预加载数据失败: {e}")

    def start(self):
        """启动WebSocket连接"""
        self._fetcher.start()

    def stop(self):
        """停止WebSocket连接"""
        self._fetcher.stop()

    def get_room_status(self):
        """获取房间状态"""
        return self._fetcher.get_room_status()

    def _wsOnMessage(self, ws, message):
        """处理WebSocket消息（重写原有方法）"""
        try:
            package = PushFrame().parse(message)
            response = Response().parse(gzip.decompress(package.payload))

            # 发送ACK确认
            if response.need_ack:
                ack = PushFrame(
                    log_id=package.log_id,
                    payload_type='ack',
                    payload=response.internal_ext.encode('utf-8')
                ).SerializeToString()
                ws.send(ack, websocket.ABNF.OPCODE_BINARY)

            # 处理消息列表
            for msg in response.messages_list:
                method = msg.method
                try:
                    if method == 'WebcastChatMessage':
                        self._handle_chat_message(ChatMessage().parse(msg.payload))
                    elif method == 'WebcastGiftMessage':
                        self._handle_gift_message(GiftMessage().parse(msg.payload))
                    elif method == 'WebcastRoomUserSeqMessage':
                        self._handle_stats_message(RoomUserSeqMessage().parse(msg.payload))
                    elif method == 'WebcastControlMessage':
                        self._handle_control_message(ControlMessage().parse(msg.payload))
                except Exception as e:
                    self.log.error(f"处理消息出错 [method={method}]: {e}")
        except Exception as e:
            self.log.error(f"解析消息出错: {e}")

    def _handle_chat_message(self, chat_msg):
        """处理聊天消息"""
        user = chat_msg.user.nick_name
        content = chat_msg.content
        level = chat_msg.user.pay_grade.level if hasattr(chat_msg.user, 'pay_grade') else 0
        
        # 处理用户ID：优先使用 id_str，如果 ID 为匿名特征值（如 111111, 0），则使用"用户名_等级"组合
        raw_id = chat_msg.user.id_str if hasattr(chat_msg.user, 'id_str') and chat_msg.user.id_str else str(chat_msg.user.id)
        if raw_id in ['0', '111111']:
            user_id = f"anon_{user}_{level}"
        else:
            user_id = raw_id

        # 获取data_service（从app全局变量或monitored_room）
        data_service = self.monitored_room.manager.data_service

        # 构建包含等级图标和用户名的消息内容
        level_img_tag = f'<img src="/level_img/level_{level}.png" class="user-level-icon" alt="等级">' if level else ''
        message_content_html = f'{level_img_tag} <span class="user-highlight">{user}</span>: {content}'

        is_gift_user = user in self.gift_users

        # 保存到数据库
        data_service.save_chat_message(
            self.room_id,
            live_session_id=self.current_session_id,
            user_id=user_id,
            user_name=user,
            user_level=level,
            content=content,
            is_gift_user=is_gift_user
        )

        # 更新场次弹幕计数
        if self.current_session_id:
            data_service.increment_session_stats(
                self.current_session_id,
                chat_count_delta=1
            )

        # 通过Socket.IO推送到前端
        message_data = {
            'type': 'chat',
            'user': user,
            'content': message_content_html,
            'is_gift_user': is_gift_user,
        }
        self.socketio.emit(f'room_{self.room_id}', message_data, room=f'room_{self.room_id}')
        self.log.info(f"发送弹幕消息: {user}: {content}")

    def _handle_gift_message(self, gift_msg):
        """处理礼物消息"""
        # 使用 trace_id 进行去重
        trace_id = getattr(gift_msg, 'trace_id', None)
        if trace_id:
            if trace_id in self.traceId_list:
                self.log.debug(f"礼物消息已处理过，跳过: trace_id={trace_id}")
                return
            self.traceId_list.append(trace_id)

        # 限制 traceId_list 大小，防止内存泄漏
        if len(self.traceId_list) > 1000:
            self.traceId_list = self.traceId_list[-500:]

        # 获取data_service
        data_service = self.monitored_room.manager.data_service

        user = gift_msg.user.nick_name
        gift_name = gift_msg.gift.name
        gift_price = gift_msg.gift.diamond_count
        level = gift_msg.user.pay_grade.level if hasattr(gift_msg.user, 'pay_grade') else 0

        # 处理用户ID：优先使用 id_str，如果 ID 为匿名特征值（如 111111, 0），则使用"用户名_等级"组合
        raw_id = gift_msg.user.id_str if hasattr(gift_msg.user, 'id_str') and gift_msg.user.id_str else str(gift_msg.user.id)
        if raw_id in ['0', '111111']:
            user_id = f"anon_{user}_{level}"
            self.log.info(f"检测到匿名用户(ID={raw_id})，生成虚拟ID: {user_id}")
        else:
            user_id = raw_id

        self.log.info(f"[礼物消息] user_id={user_id}, user_name={user}, gift_name={gift_name}, price={gift_price}, send_type={gift_msg.send_type}")

        # 处理礼物数量
        if gift_msg.send_type == 4:  # 连击礼物
            combo_key = f"{gift_msg.group_id}_{gift_msg.user.id}_{gift_msg.gift_id}"
            if gift_msg.repeat_end == 1:  # 连击结束
                gift_count = gift_msg.combo_count
                if combo_key in self.monitored_room.combo_gifts:
                    del self.monitored_room.combo_gifts[combo_key]
            else:  # 连击过程中
                if combo_key not in self.monitored_room.combo_gifts:
                    self.monitored_room.combo_gifts[combo_key] = {
                        'last_count': 0,
                        'total_value': 0
                    }
                current_count = gift_msg.combo_count
                count_diff = current_count - self.monitored_room.combo_gifts[combo_key]['last_count']
                self.monitored_room.combo_gifts[combo_key]['last_count'] = current_count
                gift_count = count_diff
        else:  # 普通礼物
            gift_count = gift_msg.group_count

        total_gift_value = gift_price * gift_count
        self.total_income += total_gift_value
        self.gift_users.add(user)

        # 更新本地统计
        self.monitored_room.stats['total_income'] = self.total_income

        # 获取用户头像
        avatar = None
        if hasattr(gift_msg.user, 'avatar_thumb') and gift_msg.user.avatar_thumb:
            avatar = gift_msg.user.avatar_thumb.url_list_list[0] if gift_msg.user.avatar_thumb.url_list_list else None

        # 更新用户贡献
        self.monitored_room.update_contribution(
            user_id,
            user,
            gift_value=total_gift_value,
            gift_count=1,
            user_avatar=avatar
        )

        # 保存到数据库
        data_service.save_gift_message(
            self.room_id,
            live_session_id=self.current_session_id,
            user_id=user_id,
            user_name=user,
            user_level=level,
            gift_id=str(gift_msg.gift_id) if hasattr(gift_msg, 'gift_id') else None,
            gift_name=gift_name,
            gift_count=gift_count,
            gift_price=gift_price,
            total_value=total_gift_value,
            send_type='combo' if gift_msg.send_type == 4 else 'normal',
            group_id=str(gift_msg.group_id) if hasattr(gift_msg, 'group_id') else None
        )

        # 更新场次统计（礼物收入和数量）
        if self.current_session_id:
            data_service.increment_session_stats(
                self.current_session_id,
                income_delta=total_gift_value,
                gift_count_delta=1
            )

        # 构建包含等级图标和用户名的消息内容
        level_img_tag = f'<img src="/level_img/level_{level}.png" class="user-level-icon" alt="等级">' if level else ''
        gift_message_content_html = f'{level_img_tag} <span class="user-highlight">{user}</span> 赠送了 {gift_count} 个 {gift_name} (价值{gift_price}钻石)'

        # 通过Socket.IO推送到前端
        message_data = {
            'type': 'gift',
            'user': user,
            'gift_name': gift_name,
            'gift_count': gift_count,
            'gift_price': gift_price,
            'total_value': total_gift_value,
            'content': gift_message_content_html
        }
        self.socketio.emit(f'room_{self.room_id}', message_data, room=f'room_{self.room_id}')
        self.log.info(f"发送礼物消息: {user} 送出了 {gift_name}x{gift_count},单价{gift_price},总价值{total_gift_value}")

    def _handle_stats_message(self, stats_msg):
        """处理统计消息"""
        current = stats_msg.total
        total = stats_msg.total_pv_for_anchor

        # 更新统计信息
        if current is not None and current >= 0:
            self.monitored_room.stats['current_user_count'] = current
            self.monitored_room.last_stats['current_user_count'] = current
            self.current_viewer_count = current

            # 更新峰值观看人数
            if current > self.max_viewer_count:
                self.max_viewer_count = current
                # 同步更新到数据库的场次记录
                if self.current_session_id:
                    data_service = self.monitored_room.manager.data_service
                    data_service.update_session_stats(
                        self.current_session_id,
                        peak_viewer_count=self.max_viewer_count
                    )

        if total is not None and total != '':
            # 将格式化的数字（如'46.8万'）转换为整数
            total_numeric = parse_formatted_number(total)
            self.monitored_room.stats['total_user_count'] = total_numeric
            self.monitored_room.last_stats['total_user_count'] = total_numeric

        self.monitored_room.stats['contributor_count'] = len(self.monitored_room.user_contributions)

        # 获取贡献榜
        rank_list = self.monitored_room.get_contribution_rank(100)

        # 通过Socket.IO推送到前端
        self.socketio.emit(f'room_{self.room_id}_stats', {
            'current_user_count': self.monitored_room.stats['current_user_count'],
            'total_user_count': self.monitored_room.stats['total_user_count'],
            'total_income': self.monitored_room.stats['total_income'],
            'contributor_count': self.monitored_room.stats['contributor_count'],
            'contributor_info': rank_list
        }, room=f'room_{self.room_id}')
        self.log.debug(f"发送直播间统计: 当前{current}, 累计{total}, 总收入{self.total_income}, 贡献者数{len(self.monitored_room.user_contributions)}")

    def _wsOnOpen(self, ws):
        """WebSocket连接建立"""
        self.log.success("WebSocket连接已建立")

        # 获取并更新主播信息
        try:
            anchor_info = self._fetcher.anchor_info
            anchor_name = anchor_info.get('anchor_name')
            if anchor_name or anchor_info.get('anchor_id'):
                data_service = self.monitored_room.manager.data_service
                data_service.update_live_room(
                    self.room_id,
                    anchor_name=anchor_name,
                    anchor_id=anchor_info.get('anchor_id')
                )

                # 获取到主播名字后，更新日志上下文：显示为 "主播名(live_id)" 或 "(live_id)"
                room_display = f"{anchor_name}({self.live_id})" if anchor_name else f"({self.live_id})"
                self.log = get_logger("handlers", room_display)

                # 同时更新核心抓取器的日志上下文
                self._fetcher.update_log_context(anchor_name)

                self.log.info(f"更新主播信息: {anchor_info}")
        except Exception as e:
            self.log.warning(f"获取主播信息失败: {e}")

        # 检查或创建直播场次
        data_service = self.monitored_room.manager.data_service
        current_session = data_service.get_current_live_session(self.room_id)

        if current_session:
            # 已有进行中的场次，继续使用
            self.current_session_id = current_session.id
            self.log.info(f"继续现有直播场次: session_id={self.current_session_id}")

            # 只有在本地缓存为空时才从数据库加载（避免覆盖已存在的实时数据）
            if not self.monitored_room.user_contributions:
                self.log.info("本地贡献榜为空，从数据库加载")
                session_contributors = data_service.get_session_contributors(self.room_id, current_session.id, limit=1000)
                for contributor in session_contributors:
                    # get_session_contributors 返回的是 Dict，使用字典访问
                    self.monitored_room.user_contributions[contributor['user_id']] = {
                        'user_name': contributor['user_name'],
                        'score': contributor['total_score'],
                        'avatar': contributor['user_avatar'],
                        'gift_count': contributor['gift_count']
                    }
                self.log.info(f"从数据库加载了 {len(session_contributors)} 个贡献者到本地缓存")
            else:
                self.log.info(f"本地已有 {len(self.monitored_room.user_contributions)} 个贡献者，跳过数据库加载")
        else:
            # 创建新的直播场次
            # 清空本地贡献榜缓存（新场次）
            old_count = len(self.monitored_room.user_contributions)
            self.monitored_room.user_contributions.clear()
            self.log.info(f"新直播场次：清空本地贡献榜缓存（清除了{old_count}个用户）")

            new_session = data_service.create_live_session(
                self.room_id,
                status='live'
            )
            if new_session:
                self.current_session_id = new_session.id
                self.current_viewer_count = 0
                self.max_viewer_count = 0
                self.log.info(f"创建新直播场次: session_id={self.current_session_id}")

        # 更新直播间状态
        data_service.update_live_room_status(self.room_id, 'monitoring')

    def _wsOnError(self, ws, error):
        """WebSocket错误"""
        error_str = str(error)
        # 502 错误是抖音服务器端问题，降低日志级别并给出更友好的提示
        if "502" in error_str or "Bad Gateway" in error_str:
            self.log.warning(f"抖音服务器暂时无响应 (502)，将在重连间隔后自动重试")
        else:
            self.log.error(f"WebSocket错误: {error}")

    def _handle_control_message(self, control_msg):
        """处理控制消息（直播状态变化）"""
        if control_msg.status == 3:
            # 直播已结束
            self.log.warning("检测到直播间已结束")

            # 结束当前直播场次
            if self.current_session_id:
                data_service = self.monitored_room.manager.data_service
                data_service.end_live_session(
                    self.current_session_id,
                    peak_viewer_count=self.max_viewer_count
                )
                self.log.info(f"结束直播场次: session_id={self.current_session_id}, 峰值观看人数={self.max_viewer_count}")
                self.current_session_id = None

                # 更新直播间状态
                data_service.update_live_room_status(self.room_id, 'stopped')

            # 停止监控
            self.stop()

    def _wsOnClose(self, ws, *args):
        """WebSocket连接关闭"""
        self.log.warning("WebSocket连接已关闭")

