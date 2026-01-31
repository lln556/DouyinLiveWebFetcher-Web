"""
配置文件
抖音直播监控平台配置
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

# 基础路径
BASE_DIR = Path(__file__).resolve().parent

# 数据库配置 - MySQL 8.0+
# 格式: mysql+pymysql://用户名:密码@主机/数据库名
DATABASE_URL = os.getenv(
    'DATABASE_URL',
    'mysql+pymysql://root:password@localhost/douyin_live'
)

# Flask配置
SECRET_KEY = os.getenv('SECRET_KEY', 'your-secret-key-change-in-production')
DEBUG = os.getenv('DEBUG', 'False') == 'True'

# 代理配置
PROXY_ENABLED = os.getenv('PROXY_ENABLED', 'False') == 'True'  # 是否启用代理
PROXY_HOST = os.getenv('PROXY_HOST', '127.0.0.1')  # 代理主机
PROXY_PORT = int(os.getenv('PROXY_PORT', '7890'))  # 代理端口
PROXY_TYPE = os.getenv('PROXY_TYPE', 'http')  # 代理类型: http, socks5

# WebSocket配置
SOCKETIO_CORS_ALLOWED_ORIGINS = os.getenv('SOCKETIO_CORS_ALLOWED_ORIGINS', '*')
SOCKETIO_LOGGER = os.getenv('SOCKETIO_LOGGER', 'False') == 'True'
SOCKETIO_ENGINEIO_LOGGER = os.getenv('SOCKETIO_ENGINEIO_LOGGER', 'False') == 'True'

# 监控配置
MONITOR_RECONNECT_INTERVAL = int(os.getenv('MONITOR_RECONNECT_INTERVAL', '30'))  # 重连间隔(秒)
MONITOR_MAX_RETRIES = int(os.getenv('MONITOR_MAX_RETRIES', '5'))  # 最大重试次数
MONITOR_RECONNECT_DELAY = int(os.getenv('MONITOR_RECONNECT_DELAY', '30'))  # 重连延迟(秒)
MONITOR_STATUS_POLL_INTERVAL = int(os.getenv('MONITOR_STATUS_POLL_INTERVAL', '60'))  # 轮询直播状态间隔(秒)

# 数据保留配置
DATA_RETENTION_DAYS = int(os.getenv('DATA_RETENTION_DAYS', '90'))  # 数据保留天数，0表示永久保留

# 日志配置
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
LOG_FILE = str(BASE_DIR / 'logs' / 'app.log')

# 调度器配置
SCHEDULER_RESTART_FAILED_INTERVAL = int(os.getenv('SCHEDULER_RESTART_FAILED_INTERVAL', '30'))  # 检查失败房间间隔(秒)
SCHEDULER_STATS_SNAPSHOT_INTERVAL = int(os.getenv('SCHEDULER_STATS_SNAPSHOT_INTERVAL', '60'))  # 保存统计快照间隔(秒)
SCHEDULER_CLEANUPOldData_INTERVAL = int(os.getenv('SCHEDULER_CLEANUPOldData_INTERVAL', '3600'))  # 清理旧数据间隔(秒)

# WebSocket配置
WS_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36 Edg/140.0.0.0"
WS_HOST = "https://www.douyin.com/"
WS_LIVE_URL = "https://live.douyin.com/"

# 确保必要的目录存在
os.makedirs(BASE_DIR / 'data', exist_ok=True)
os.makedirs(BASE_DIR / 'logs', exist_ok=True)


def get_proxy_config():
    """获取代理配置"""
    if not PROXY_ENABLED:
        return None
    proxy_url = f"{PROXY_TYPE}://{PROXY_HOST}:{PROXY_PORT}"
    return {
        'http': proxy_url,
        'https': proxy_url
    }


def get_proxy_url():
    """获取代理URL（用于WebSocket）"""
    if not PROXY_ENABLED:
        return None
    return f"{PROXY_TYPE}://{PROXY_HOST}:{PROXY_PORT}"
