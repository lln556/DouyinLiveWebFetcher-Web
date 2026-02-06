"""
房间管理API路由
"""
from flask import Blueprint, request, jsonify

from services.data_service import DataService
from utils.logger import get_logger

logger = get_logger("api_rooms")

# 创建蓝图
rooms_bp = Blueprint('rooms', __name__, url_prefix='/api/rooms')


def init_rooms_api(data_service: DataService, room_manager, socketio):
    """初始化房间API路由"""

    @rooms_bp.route('', methods=['GET'])
    def list_rooms():
        """获取房间列表"""
        try:
            status = request.args.get('status')
            rooms = data_service.list_live_rooms(status=status)

            # 获取活跃状态
            active_status = {}
            for live_id, monitored_room in room_manager.active_rooms.items():
                active_status[live_id] = {
                    'is_active': monitored_room.thread and monitored_room.thread.is_alive(),
                    'stats': monitored_room.get_stats()
                }

            result = []
            for room in rooms:
                # 获取活跃状态
                stats = {}
                is_active = False
                if room.live_id in active_status:
                    is_active = active_status[room.live_id]['is_active']
                    stats = active_status[room.live_id]['stats']

                # 判断直播状态：有人在线即为直播中
                live_status = 'live' if stats.get('current_user_count', 0) > 0 else 'offline'

                room_dict = {
                    'live_id': room.live_id,
                    'anchor_name': room.anchor_name,
                    'anchor_id': room.anchor_id,
                    'monitor_status': room.status,  # 监控状态: monitoring/stopped/error
                    'live_status': live_status,  # 直播状态: live/offline
                    'status': room.status,  # 兼容旧版
                    'monitor_type': room.monitor_type,
                    'auto_reconnect': room.auto_reconnect,
                    'reconnect_count': room.reconnect_count,
                    'created_at': room.created_at.isoformat() if room.created_at else None,
                    'updated_at': room.updated_at.isoformat() if room.updated_at else None,
                    'is_active': is_active,
                    'stats': stats
                }

                result.append(room_dict)

            return jsonify({'rooms': result})
        except Exception as e:
            logger.error(f"获取房间列表失败: {e}")
            return jsonify({'error': str(e)}), 500

    @rooms_bp.route('', methods=['POST'])
    def add_room():
        """添加监控房间"""
        try:
            data = request.get_json()
            live_id = data.get('live_id')

            if not live_id:
                return jsonify({'error': '请提供直播间ID'}), 400

            monitor_type = data.get('monitor_type', 'manual')
            auto_reconnect = data.get('auto_reconnect', False)

            # 添加到管理器
            result_live_id = room_manager.add_room(live_id, monitor_type, auto_reconnect)

            if result_live_id is None:
                return jsonify({'error': '该直播间已在监控中'}), 400

            room = data_service.get_live_room(result_live_id)

            return jsonify({
                'message': '房间添加成功',
                'room': {
                    'live_id': room.live_id,
                    'anchor_name': room.anchor_name,
                    'status': room.status,
                    'monitor_type': room.monitor_type,
                    'auto_reconnect': room.auto_reconnect
                }
            })
        except Exception as e:
            logger.error(f"添加房间失败: {e}")
            return jsonify({'error': str(e)}), 500

    @rooms_bp.route('/<live_id>', methods=['GET'])
    def get_room(live_id):
        """获取房间详情"""
        try:
            room = data_service.get_live_room(live_id)
            if not room:
                return jsonify({'error': '房间不存在'}), 404

            # 获取监控中的房间实例
            monitored_room = room_manager.get_room(live_id)
            stats = None
            is_active = False
            if monitored_room:
                stats = monitored_room.get_stats()
                is_active = monitored_room.thread and monitored_room.thread.is_alive()

            return jsonify({
                'room': {
                    'live_id': room.live_id,
                    'anchor_name': room.anchor_name,
                    'anchor_id': room.anchor_id,
                    'status': room.status,
                    'monitor_type': room.monitor_type,
                    'auto_reconnect': room.auto_reconnect,
                    'reconnect_count': room.reconnect_count,
                    'last_connect_time': room.last_connect_time.isoformat() if room.last_connect_time else None,
                    'last_disconnect_time': room.last_disconnect_time.isoformat() if room.last_disconnect_time else None,
                    'error_message': room.error_message,
                    'created_at': room.created_at.isoformat() if room.created_at else None,
                    'updated_at': room.updated_at.isoformat() if room.updated_at else None,
                    'is_active': is_active,
                    'stats': stats
                }
            })
        except Exception as e:
            logger.error(f"获取房间详情失败: {e}")
            return jsonify({'error': str(e)}), 500

    @rooms_bp.route('/<live_id>/start', methods=['POST'])
    def start_room(live_id):
        """启动房间监控"""
        try:
            # 确保房间在活跃列表中
            if live_id not in room_manager.active_rooms:
                room = data_service.get_live_room(live_id)
                if not room:
                    return jsonify({'error': '房间不存在'}), 404

                # 重新添加到管理器
                result_live_id = room_manager.add_room(
                    room.live_id,
                    room.monitor_type,
                    room.auto_reconnect
                )
                if result_live_id != live_id:
                    return jsonify({'error': '重新添加房间失败'}), 500

            # 启动监控
            if room_manager.start_room(live_id):
                return jsonify({'message': '房间监控已启动'})
            else:
                return jsonify({'error': '启动监控失败'}), 500
        except Exception as e:
            logger.error(f"启动房间监控失败: {e}")
            return jsonify({'error': str(e)}), 500

    @rooms_bp.route('/<live_id>/stop', methods=['POST'])
    def stop_room(live_id):
        """停止房间监控"""
        try:
            if room_manager.stop_room(live_id):
                return jsonify({'message': '房间监控已停止'})
            else:
                return jsonify({'error': '房间不存在或未在监控中'}), 404
        except Exception as e:
            logger.error(f"停止房间监控失败: {e}")
            return jsonify({'error': str(e)}), 500

    @rooms_bp.route('/<live_id>', methods=['DELETE'])
    def delete_room(live_id):
        """删除房间"""
        try:
            # 先停止监控
            room_manager.remove_room(live_id)

            # 从数据库删除
            if data_service.delete_live_room(live_id):
                return jsonify({'message': '房间已删除'})
            else:
                return jsonify({'error': '房间不存在'}), 404
        except Exception as e:
            logger.error(f"删除房间失败: {e}")
            return jsonify({'error': str(e)}), 500

    @rooms_bp.route('/<live_id>/messages', methods=['GET'])
    def get_room_messages(live_id):
        """获取房间消息（支持分页）"""
        try:
            page_size = min(int(request.args.get('limit', 50)), 1000)
            page = max(int(request.args.get('page', 1)), 1)
            offset = int(request.args.get('offset', (page - 1) * page_size))
            msg_type = request.args.get('type', 'all')  # chat/gift/all

            # 获取消息总数
            counts = data_service.get_message_counts(live_id)

            if msg_type == 'chat':
                total = counts['chat_count']
                messages = data_service.get_chat_messages(live_id, page_size, offset)
                messages_data = [
                    {
                        'id': msg.id,
                        'type': 'chat',
                        'live_id': msg.live_id,
                        'anchor_name': msg.anchor_name,
                        'user_name': msg.user_name,
                        'user_level': msg.user_level,
                        'content': msg.content,
                        'is_gift_user': msg.is_gift_user,
                        'created_at': msg.created_at.isoformat() if msg.created_at else None
                    }
                    for msg in messages
                ]
            elif msg_type == 'gift':
                total = counts['gift_count']
                messages = data_service.get_gift_messages(live_id, page_size, offset)
                messages_data = [
                    {
                        'id': msg.id,
                        'type': 'gift',
                        'live_id': msg.live_id,
                        'anchor_name': msg.anchor_name,
                        'user_name': msg.user_name,
                        'user_level': msg.user_level,
                        'gift_name': msg.gift_name,
                        'gift_count': msg.gift_count,
                        'gift_price': msg.gift_price,
                        'total_value': msg.total_value,
                        'send_type': msg.send_type,
                        'created_at': msg.created_at.isoformat() if msg.created_at else None
                    }
                    for msg in messages
                ]
            else:  # all
                total = counts['total_count']
                messages_data = data_service.get_all_messages(live_id, page_size, offset)

            total_pages = (total + page_size - 1) // page_size if total > 0 else 1

            return jsonify({
                'messages': messages_data,
                'pagination': {
                    'total': total,
                    'page': page,
                    'page_size': page_size,
                    'total_pages': total_pages
                },
                'counts': counts
            })
        except Exception as e:
            logger.error(f"获取房间消息失败: {e}")
            return jsonify({'error': str(e)}), 500

    @rooms_bp.route('/<live_id>/contributors', methods=['GET'])
    def get_room_contributors(live_id):
        """获取房间贡献榜"""
        try:
            limit = min(int(request.args.get('limit', 100)), 1000)
            contributors = data_service.get_top_contributors(live_id, limit)

            return jsonify({
                'contributors': [
                    {
                        'live_id': c.live_id,
                        'anchor_name': c.anchor_name,
                        'user_id': c.user_id,
                        'user_name': c.user_name,
                        'total_score': c.total_score,
                        'gift_count': c.gift_count,
                        'chat_count': c.chat_count,
                        'user_avatar': c.user_avatar
                    }
                    for c in contributors
                ]
            })
        except Exception as e:
            logger.error(f"获取房间贡献榜失败: {e}")
            return jsonify({'error': str(e)}), 500

    @rooms_bp.route('/<live_id>/session-contributors', methods=['GET'])
    def get_session_contributors(live_id):
        """获取当前直播场次的贡献榜"""
        try:
            # 获取当前直播场次
            current_session = data_service.get_current_live_session(live_id)
            if not current_session:
                return jsonify({'contributors': [], 'message': '暂无进行中的直播场次'})

            limit = min(int(request.args.get('limit', 100)), 1000)
            contributors = data_service.get_session_contributors(live_id, current_session.id, limit)

            return jsonify({
                'session_id': current_session.id,
                'live_id': live_id,
                'contributors': contributors
            })
        except Exception as e:
            logger.error(f"获取场次贡献榜失败: {e}")
            return jsonify({'error': str(e)}), 500

    @rooms_bp.route('/<live_id>/stats', methods=['GET'])
    def get_room_stats(live_id):
        """获取房间统计"""
        try:
            hours = int(request.args.get('hours', 24))
            stats_history = data_service.get_room_stats_history(live_id, hours)
            latest_stats = data_service.get_latest_stats(live_id)

            # 获取实时统计（如果正在监控）
            monitored_room = room_manager.get_room(live_id)
            realtime_stats = None
            if monitored_room and monitored_room.thread and monitored_room.thread.is_alive():
                realtime_stats = monitored_room.get_stats()

            return jsonify({
                'latest': {
                    'live_id': latest_stats.live_id if latest_stats else None,
                    'anchor_name': latest_stats.anchor_name if latest_stats else None,
                    'current_user_count': latest_stats.current_user_count if latest_stats else 0,
                    'total_user_count': latest_stats.total_user_count if latest_stats else 0,
                    'total_income': latest_stats.total_income if latest_stats else 0,
                    'contributor_count': latest_stats.contributor_count if latest_stats else 0,
                    'stats_at': latest_stats.stats_at.isoformat() if latest_stats else None
                } if latest_stats else None,
                'realtime': realtime_stats,
                'history': [
                    {
                        'live_id': s.live_id,
                        'anchor_name': s.anchor_name,
                        'current_user_count': s.current_user_count,
                        'total_user_count': s.total_user_count,
                        'total_income': s.total_income,
                        'contributor_count': s.contributor_count,
                        'stats_at': s.stats_at.isoformat() if s.stats_at else None
                    }
                    for s in stats_history
                ]
            })
        except Exception as e:
            logger.error(f"获取房间统计失败: {e}")
            return jsonify({'error': str(e)}), 500

    @rooms_bp.route('/stats/summary', methods=['GET'])
    def get_stats_summary():
        """获取全局统计摘要"""
        try:
            summary = data_service.get_stats_summary()
            return jsonify(summary)
        except Exception as e:
            logger.error(f"获取统计摘要失败: {e}")
            return jsonify({'error': str(e)}), 500

    @rooms_bp.route('/<live_id>/current-session', methods=['GET'])
    def get_current_session(live_id):
        """获取当前直播场次数据"""
        try:
            # 先检查房间是否存在
            room = data_service.get_live_room(live_id)
            if not room:
                return jsonify({'error': '房间不存在'}), 404

            # 获取当前进行中的直播场次
            current_session = data_service.get_current_live_session(live_id)

            # 如果没有进行中的场次，尝试获取最近结束的场次
            if not current_session:
                recent_sessions = data_service.get_live_sessions(live_id, status='ended', limit=1)
                if recent_sessions:
                    current_session = recent_sessions[0]

            if not current_session:
                return jsonify({'session': None, 'message': '暂无直播场次数据'})

            return jsonify({
                'session': {
                    'id': current_session.id,
                    'live_id': current_session.live_id,
                    'anchor_name': current_session.anchor_name,
                    'start_time': current_session.start_time.isoformat() if current_session.start_time else None,
                    'end_time': current_session.end_time.isoformat() if current_session.end_time else None,
                    'status': current_session.status,
                    'total_income': current_session.total_income,
                    'total_gift_count': current_session.total_gift_count,
                    'total_chat_count': current_session.total_chat_count,
                    'peak_viewer_count': current_session.peak_viewer_count
                }
            })
        except Exception as e:
            logger.error(f"获取当前直播场次失败: {e}")
            return jsonify({'error': str(e)}), 500

    @rooms_bp.route('/<live_id>/sessions', methods=['GET'])
    def get_room_sessions(live_id):
        """获取房间的直播场次列表"""
        try:
            # 先检查房间是否存在
            room = data_service.get_live_room(live_id)
            if not room:
                return jsonify({'error': '房间不存在'}), 404

            start_date = request.args.get('start_date')
            end_date = request.args.get('end_date')
            limit = min(int(request.args.get('limit', 50)), 200)
            logger.info(f"获取场次列表: live_id={live_id}, start_date={start_date}, end_date={end_date}")

            sessions = data_service.get_room_sessions_stats(live_id, start_date, end_date, limit)
            logger.info(f"场次列表结果: 共 {len(sessions)} 条")

            return jsonify({'sessions': sessions})
        except Exception as e:
            logger.error(f"获取直播场次列表失败: {e}")
            return jsonify({'error': str(e)}), 500

    @rooms_bp.route('/<live_id>/sessions/stats', methods=['GET'])
    def get_room_sessions_stats(live_id):
        """获取房间的聚合统计数据"""
        try:
            # 先检查房间是否存在
            room = data_service.get_live_room(live_id)
            if not room:
                return jsonify({'error': '房间不存在'}), 404

            start_date = request.args.get('start_date')
            end_date = request.args.get('end_date')
            logger.info(f"获取房间统计: live_id={live_id}, start_date={start_date}, end_date={end_date}")

            stats = data_service.get_sessions_aggregated_stats(live_id, start_date, end_date)
            logger.info(f"房间统计结果: {stats}")

            return jsonify({'stats': stats})
        except Exception as e:
            logger.error(f"获取聚合统计数据失败: {e}")
            return jsonify({'error': str(e)}), 500

    @rooms_bp.route('/<live_id>/config', methods=['PUT', 'PATCH'])
    def update_room_config(live_id):
        """更新房间配置（监控类型、自动重连等）"""
        try:
            # 先检查房间是否存在
            room = data_service.get_live_room(live_id)
            if not room:
                return jsonify({'error': '房间不存在'}), 404

            data = request.get_json()
            monitor_type = data.get('monitor_type')
            auto_reconnect = data.get('auto_reconnect')

            # 验证 monitor_type
            if monitor_type is not None and monitor_type not in ['manual', '24h']:
                return jsonify({'error': '监控类型必须是 manual 或 24h'}), 400

            # 更新数据库
            update_data = {}
            if monitor_type is not None:
                update_data['monitor_type'] = monitor_type
            if auto_reconnect is not None:
                update_data['auto_reconnect'] = auto_reconnect

            if update_data:
                data_service.update_live_room(live_id, **update_data)
                logger.info(f"更新房间 {live_id} 配置: {update_data}")

            # 获取更新后的房间信息
            updated_room = data_service.get_live_room(live_id)

            # 如果房间正在监控中，更新其配置
            monitored_room = room_manager.get_room(live_id)

            return jsonify({
                'message': '房间配置已更新',
                'room': {
                    'live_id': updated_room.live_id,
                    'anchor_name': updated_room.anchor_name,
                    'monitor_type': updated_room.monitor_type,
                    'auto_reconnect': updated_room.auto_reconnect,
                    'status': updated_room.status
                }
            })
        except Exception as e:
            logger.error(f"更新房间配置失败: {e}")
            return jsonify({'error': str(e)}), 500

    @rooms_bp.route('/sessions/stats', methods=['GET'])
    def get_all_sessions_stats():
        """获取全局聚合统计数据"""
        try:
            start_date = request.args.get('start_date')
            end_date = request.args.get('end_date')
            logger.info(f"获取全局统计: start_date={start_date}, end_date={end_date}")

            stats = data_service.get_sessions_aggregated_stats(None, start_date, end_date)
            logger.info(f"全局统计结果: {stats}")

            return jsonify({'stats': stats})
        except Exception as e:
            logger.error(f"获取全局聚合统计数据失败: {e}")
            return jsonify({'error': str(e)}), 500

    @rooms_bp.route('/sessions/<int:session_id>', methods=['GET'])
    def get_session_detail(session_id):
        """获取直播场次详情（弹幕、礼物、贡献榜）"""
        try:
            page_size = min(int(request.args.get('limit', 50)), 200)
            page = max(int(request.args.get('page', 1)), 1)
            offset = (page - 1) * page_size
            msg_type = request.args.get('type', 'chat')  # chat/gift/contributors
            logger.info(f"获取场次详情: session_id={session_id}, page={page}, page_size={page_size}, type={msg_type}")

            # 获取场次基本信息
            session_obj = data_service.get_live_session_stats(session_id)
            if not session_obj:
                return jsonify({'error': '场次不存在'}), 404

            # 获取消息总数
            counts = data_service.get_session_message_counts(session_id)

            result = {
                'session': session_obj,
                'counts': counts
            }

            # 根据请求类型返回对应数据
            if msg_type == 'chat':
                messages = data_service.get_session_messages(session_id, 'chat', page_size, offset)
                total = counts['chat_count']
                result['chats'] = messages
                result['pagination'] = {
                    'total': total,
                    'page': page,
                    'page_size': page_size,
                    'total_pages': (total + page_size - 1) // page_size if total > 0 else 1
                }
            elif msg_type == 'gift':
                messages = data_service.get_session_messages(session_id, 'gift', page_size, offset)
                total = counts['gift_count']
                result['gifts'] = messages
                result['pagination'] = {
                    'total': total,
                    'page': page,
                    'page_size': page_size,
                    'total_pages': (total + page_size - 1) // page_size if total > 0 else 1
                }
            elif msg_type == 'contributors':
                contributors = data_service.get_session_contributors(session_obj['live_id'], session_id, 100)
                result['contributors'] = contributors
            else:
                # 兼容旧的调用方式，返回所有数据（但只返回第一页）
                result['chats'] = data_service.get_session_messages(session_id, 'chat', page_size, 0)
                result['gifts'] = data_service.get_session_messages(session_id, 'gift', page_size, 0)
                result['contributors'] = data_service.get_session_contributors(session_obj['live_id'], session_id, 100)

            return jsonify(result)
        except Exception as e:
            logger.error(f"获取场次详情失败: {e}")
            return jsonify({'error': str(e)}), 500

    return rooms_bp
