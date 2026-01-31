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
            for room_id, monitored_room in room_manager.active_rooms.items():
                active_status[room_id] = {
                    'is_active': monitored_room.thread and monitored_room.thread.is_alive(),
                    'stats': monitored_room.get_stats()
                }

            result = []
            for room in rooms:
                room_dict = {
                    'id': room.id,
                    'live_id': room.live_id,
                    'room_id': room.room_id,
                    'anchor_name': room.anchor_name,
                    'anchor_id': room.anchor_id,
                    'status': room.status,
                    'monitor_type': room.monitor_type,
                    'auto_reconnect': room.auto_reconnect,
                    'reconnect_count': room.reconnect_count,
                    'created_at': room.created_at.isoformat() if room.created_at else None,
                    'updated_at': room.updated_at.isoformat() if room.updated_at else None,
                }

                # 添加活跃状态
                if room.id in active_status:
                    room_dict.update(active_status[room.id])

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
            room_id = room_manager.add_room(live_id, monitor_type, auto_reconnect)

            if room_id is None:
                return jsonify({'error': '该直播间已在监控中'}), 400

            room = data_service.get_live_room(room_id)

            return jsonify({
                'message': '房间添加成功',
                'room': {
                    'id': room.id,
                    'live_id': room.live_id,
                    'status': room.status,
                    'monitor_type': room.monitor_type,
                    'auto_reconnect': room.auto_reconnect
                }
            })
        except Exception as e:
            logger.error(f"添加房间失败: {e}")
            return jsonify({'error': str(e)}), 500

    @rooms_bp.route('/<int:room_id>', methods=['GET'])
    def get_room(room_id):
        """获取房间详情"""
        try:
            room = data_service.get_live_room(room_id)
            if not room:
                return jsonify({'error': '房间不存在'}), 404

            # 获取监控中的房间实例
            monitored_room = room_manager.get_room(room_id)
            stats = None
            is_active = False
            if monitored_room:
                stats = monitored_room.get_stats()
                is_active = monitored_room.thread and monitored_room.thread.is_alive()

            return jsonify({
                'room': {
                    'id': room.id,
                    'live_id': room.live_id,
                    'room_id': room.room_id,
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

    @rooms_bp.route('/<int:room_id>/start', methods=['POST'])
    def start_room(room_id):
        """启动房间监控"""
        try:
            # 确保房间在活跃列表中
            if room_id not in room_manager.active_rooms:
                room = data_service.get_live_room(room_id)
                if not room:
                    return jsonify({'error': '房间不存在'}), 404

                # 重新添加到管理器
                new_room_id = room_manager.add_room(
                    room.live_id,
                    room.monitor_type,
                    room.auto_reconnect
                )
                if new_room_id != room_id:
                    return jsonify({'error': '重新添加房间失败'}), 500

            # 启动监控
            if room_manager.start_room(room_id):
                return jsonify({'message': '房间监控已启动'})
            else:
                return jsonify({'error': '启动监控失败'}), 500
        except Exception as e:
            logger.error(f"启动房间监控失败: {e}")
            return jsonify({'error': str(e)}), 500

    @rooms_bp.route('/<int:room_id>/stop', methods=['POST'])
    def stop_room(room_id):
        """停止房间监控"""
        try:
            if room_manager.stop_room(room_id):
                return jsonify({'message': '房间监控已停止'})
            else:
                return jsonify({'error': '房间不存在或未在监控中'}), 404
        except Exception as e:
            logger.error(f"停止房间监控失败: {e}")
            return jsonify({'error': str(e)}), 500

    @rooms_bp.route('/<int:room_id>', methods=['DELETE'])
    def delete_room(room_id):
        """删除房间"""
        try:
            # 先停止监控
            room_manager.remove_room(room_id)

            # 从数据库删除
            if data_service.delete_live_room(room_id):
                return jsonify({'message': '房间已删除'})
            else:
                return jsonify({'error': '房间不存在'}), 404
        except Exception as e:
            logger.error(f"删除房间失败: {e}")
            return jsonify({'error': str(e)}), 500

    @rooms_bp.route('/<int:room_id>/messages', methods=['GET'])
    def get_room_messages(room_id):
        """获取房间消息"""
        try:
            limit = min(int(request.args.get('limit', 100)), 1000)
            offset = int(request.args.get('offset', 0))
            msg_type = request.args.get('type')  # chat/gift/all

            if msg_type == 'chat':
                messages = data_service.get_chat_messages(room_id, limit, offset)
                return jsonify({
                    'messages': [
                        {
                            'id': msg.id,
                            'user_name': msg.user_name,
                            'user_level': msg.user_level,
                            'content': msg.content,
                            'is_gift_user': msg.is_gift_user,
                            'created_at': msg.created_at.isoformat() if msg.created_at else None
                        }
                        for msg in messages
                    ]
                })
            elif msg_type == 'gift':
                messages = data_service.get_gift_messages(room_id, limit, offset)
                return jsonify({
                    'messages': [
                        {
                            'id': msg.id,
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
                })
            else:  # all
                messages = data_service.get_all_messages(room_id, limit)
                return jsonify({'messages': messages})
        except Exception as e:
            logger.error(f"获取房间消息失败: {e}")
            return jsonify({'error': str(e)}), 500

    @rooms_bp.route('/<int:room_id>/contributors', methods=['GET'])
    def get_room_contributors(room_id):
        """获取房间贡献榜"""
        try:
            limit = min(int(request.args.get('limit', 100)), 1000)
            contributors = data_service.get_top_contributors(room_id, limit)

            return jsonify({
                'contributors': [
                    {
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

    @rooms_bp.route('/<int:room_id>/session-contributors', methods=['GET'])
    def get_session_contributors(room_id):
        """获取当前直播场次的贡献榜"""
        try:
            # 获取当前直播场次
            current_session = data_service.get_current_live_session(room_id)
            if not current_session:
                return jsonify({'contributors': [], 'message': '暂无进行中的直播场次'})

            limit = min(int(request.args.get('limit', 100)), 1000)
            contributors = data_service.get_session_contributors(room_id, current_session.id, limit)

            return jsonify({
                'session_id': current_session.id,
                'contributors': contributors
            })
        except Exception as e:
            logger.error(f"获取场次贡献榜失败: {e}")
            return jsonify({'error': str(e)}), 500

    @rooms_bp.route('/<int:room_id>/stats', methods=['GET'])
    def get_room_stats(room_id):
        """获取房间统计"""
        try:
            hours = int(request.args.get('hours', 24))
            stats_history = data_service.get_room_stats_history(room_id, hours)
            latest_stats = data_service.get_latest_stats(room_id)

            # 获取实时统计（如果正在监控）
            monitored_room = room_manager.get_room(room_id)
            realtime_stats = None
            if monitored_room and monitored_room.thread and monitored_room.thread.is_alive():
                realtime_stats = monitored_room.get_stats()

            return jsonify({
                'latest': {
                    'current_user_count': latest_stats.current_user_count if latest_stats else 0,
                    'total_user_count': latest_stats.total_user_count if latest_stats else 0,
                    'total_income': latest_stats.total_income if latest_stats else 0,
                    'contributor_count': latest_stats.contributor_count if latest_stats else 0,
                    'stats_at': latest_stats.stats_at.isoformat() if latest_stats else None
                } if latest_stats else None,
                'realtime': realtime_stats,
                'history': [
                    {
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

    @rooms_bp.route('/<int:room_id>/current-session', methods=['GET'])
    def get_current_session(room_id):
        """获取当前直播场次数据"""
        try:
            # 先检查房间是否存在
            room = data_service.get_live_room(room_id)
            if not room:
                return jsonify({'error': '房间不存在'}), 404

            # 获取当前进行中的直播场次
            current_session = data_service.get_current_live_session(room_id)

            # 如果没有进行中的场次，尝试获取最近结束的场次
            if not current_session:
                recent_sessions = data_service.get_live_sessions(room_id, status='ended', limit=1)
                if recent_sessions:
                    current_session = recent_sessions[0]

            if not current_session:
                return jsonify({'session': None, 'message': '暂无直播场次数据'})

            return jsonify({
                'session': {
                    'id': current_session.id,
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

    @rooms_bp.route('/<int:room_id>/sessions', methods=['GET'])
    def get_room_sessions(room_id):
        """获取房间的直播场次列表"""
        try:
            # 先检查房间是否存在
            room = data_service.get_live_room(room_id)
            if not room:
                return jsonify({'error': '房间不存在'}), 404

            start_date = request.args.get('start_date')
            end_date = request.args.get('end_date')
            limit = min(int(request.args.get('limit', 50)), 200)

            sessions = data_service.get_room_sessions_stats(room_id, start_date, end_date, limit)

            return jsonify({'sessions': sessions})
        except Exception as e:
            logger.error(f"获取直播场次列表失败: {e}")
            return jsonify({'error': str(e)}), 500

    @rooms_bp.route('/<int:room_id>/sessions/stats', methods=['GET'])
    def get_room_sessions_stats(room_id):
        """获取房间的聚合统计数据"""
        try:
            # 先检查房间是否存在
            room = data_service.get_live_room(room_id)
            if not room:
                return jsonify({'error': '房间不存在'}), 404

            start_date = request.args.get('start_date')
            end_date = request.args.get('end_date')

            stats = data_service.get_sessions_aggregated_stats(room_id, start_date, end_date)

            return jsonify({'stats': stats})
        except Exception as e:
            logger.error(f"获取聚合统计数据失败: {e}")
            return jsonify({'error': str(e)}), 500

    @rooms_bp.route('/<int:room_id>/config', methods=['PUT', 'PATCH'])
    def update_room_config(room_id):
        """更新房间配置（监控类型、自动重连等）"""
        try:
            # 先检查房间是否存在
            room = data_service.get_live_room(room_id)
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
                data_service.update_live_room(room_id, **update_data)
                logger.info(f"更新房间 {room_id} 配置: {update_data}")

            # 获取更新后的房间信息
            updated_room = data_service.get_live_room(room_id)

            # 如果房间正在监控中，更新其配置
            monitored_room = room_manager.get_room(room_id)

            return jsonify({
                'message': '房间配置已更新',
                'room': {
                    'id': updated_room.id,
                    'live_id': updated_room.live_id,
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

            stats = data_service.get_sessions_aggregated_stats(None, start_date, end_date)

            return jsonify({'stats': stats})
        except Exception as e:
            logger.error(f"获取全局聚合统计数据失败: {e}")
            return jsonify({'error': str(e)}), 500

    return rooms_bp
