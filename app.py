"""
抖音直播监控平台 - Flask应用入口
支持多直播间24小时监控、数据持久化存储
"""
import os
from datetime import datetime

from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit, join_room

import config
from models.database import Base
from services.data_service import DataService
from services.room_manager import RoomManager, MonitoredRoom
from services.scheduler_service import SchedulerService
from api.rooms import init_rooms_api
from utils.logger import get_logger

# 使用 loguru 全局日志
logger = get_logger("app")

# 创建Flask应用
app = Flask(__name__)
app.config['SECRET_KEY'] = config.SECRET_KEY

# 创建Socket.IO实例
socketio = SocketIO(
    app,
    cors_allowed_origins=config.SOCKETIO_CORS_ALLOWED_ORIGINS,
    logger=config.SOCKETIO_LOGGER,
    engineio_logger=config.SOCKETIO_ENGINEIO_LOGGER
)

# 初始化服务
data_service = DataService(config.DATABASE_URL)
# 创建数据库表
data_service.create_tables()

# 初始化房间管理器
room_manager = RoomManager(data_service, socketio)

# 初始化调度服务
scheduler_service = SchedulerService(room_manager, data_service)


# ==================== 路由定义 ====================

# 静态文件路由
@app.route('/level_img/<path:filename>')
def serve_level_img(filename):
    """提供等级图标静态文件"""
    return send_from_directory('data/level_img', filename)


@app.route('/')
def index():
    """首页 - 房间列表"""
    return render_template('index.html')


@app.route('/room/<int:room_id>')
def room_detail(room_id):
    """房间详情页"""
    room = data_service.get_live_room(room_id)
    if not room:
        return "房间不存在", 404
    return render_template('room.html', room_id=room_id, live_id=room.live_id)


@app.route('/stats')
def stats_page():
    """数据统计页"""
    return render_template('stats.html')


@app.route('/api/proxy', methods=['GET'])
def get_proxy_config():
    """获取代理配置"""
    return jsonify({
        'enabled': config.PROXY_ENABLED,
        'host': config.PROXY_HOST,
        'port': config.PROXY_PORT,
        'type': config.PROXY_TYPE
    })


@app.route('/api/proxy', methods=['POST'])
def update_proxy_config():
    """更新代理配置（仅限运行时，重启后恢复为配置文件值）"""
    data = request.get_json()
    enabled = data.get('enabled', False)

    # 更新运行时配置
    config.PROXY_ENABLED = enabled
    if 'host' in data:
        config.PROXY_HOST = data['host']
    if 'port' in data:
        config.PROXY_PORT = int(data['port'])
    if 'type' in data:
        config.PROXY_TYPE = data['type']

    logger.info(f"代理配置已更新: enabled={enabled}, host={config.PROXY_HOST}, port={config.PROXY_PORT}")

    return jsonify({
        'success': True,
        'enabled': config.PROXY_ENABLED,
        'host': config.PROXY_HOST,
        'port': config.PROXY_PORT,
        'type': config.PROXY_TYPE
    })


# ==================== Socket.IO事件 ====================

@socketio.on('connect')
def handle_connect():
    """客户端连接"""
    logger.info(f"客户端连接: {request.sid}")


@socketio.on('disconnect')
def handle_disconnect():
    """客户端断开"""
    logger.info(f"客户端断开: {request.sid}")


@socketio.on('join')
def handle_join(data):
    """客户端加入房间"""
    room_id = data.get('room_id')
    if room_id:
        join_room(f'room_{room_id}')
        logger.info(f"客户端 {request.sid} 加入房间 {room_id}")
        emit('joined', {'room_id': room_id})


# ==================== 应用启动和关闭 ====================

def before_first_request():
    """首次请求前执行"""
    # 自动启动所有24小时监控房间
    rooms_24h = data_service.get_24h_monitor_rooms()
    for room in rooms_24h:
        room_id = room_manager.add_room(room.live_id, monitor_type='24h', auto_reconnect=True)
        if room_id:
            room_manager.start_room(room_id)
            logger.info(f"自动启动24小时监控: {room.live_id}")


# 初始化API路由
rooms_bp = init_rooms_api(data_service, room_manager, socketio)
app.register_blueprint(rooms_bp)


@app.before_request
def initialize():
    """每个请求前检查初始化"""
    if not hasattr(app, '_initialized'):
        app._initialized = True
        before_first_request()


@socketio.on('shutdown')
def handle_shutdown():
    """关闭应用"""
    logger.info("正在关闭应用...")
    room_manager.shutdown()
    scheduler_service.stop()
    data_service.close_session()


if __name__ == '__main__':
    try:
        # 启动调度服务
        scheduler_service.start()

        logger.info("抖音直播监控平台启动中...")
        logger.info(f"数据库: {config.DATABASE_URL}")

        # 运行Flask应用
        socketio.run(
            app,
            debug=config.DEBUG,
            host='0.0.0.0',
            port=7654,
            allow_unsafe_werkzeug=True
        )
    except KeyboardInterrupt:
        logger.info("收到中断信号，正在关闭...")
        room_manager.shutdown()
        scheduler_service.stop()
        data_service.close_session()
    finally:
        logger.info("应用已关闭")
