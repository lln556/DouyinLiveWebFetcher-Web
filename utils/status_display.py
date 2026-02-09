"""
终端状态面板
使用 rich.Live + rich.Table 动态刷新显示所有房间状态
"""
import threading
from datetime import datetime

from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.text import Text

from models.database import CHINA_TZ

# 共享 Console 实例，loguru 的控制台输出也通过此实例路由
# 当 Live 处于活跃状态时，console.print() 的输出会自动渲染在面板上方
console = Console(stderr=True)

# 状态颜色映射
STATUS_STYLES = {
    'monitoring': 'bold green',
    'offline': 'yellow',
    'waiting': 'yellow',
    'error': 'bold red',
    'stopped': 'dim',
}

# 状态中文映射
STATUS_LABELS = {
    'monitoring': '监控中',
    'offline': '轮询中',
    'waiting': '等待中',
    'error': '错误',
    'stopped': '已停止',
}

# 直播状态映射
LIVE_STATUS_LABELS = {
    'monitoring': '直播中',
    'offline': '未开播',
    'waiting': '未开播',
    'error': '未知',
    'stopped': '未开播',
}


class StatusDisplay:
    """终端状态面板，使用 rich.Live 动态刷新房间状态表"""

    def __init__(self, room_manager, refresh_interval: float = 5.0):
        """
        :param room_manager: RoomManager 实例
        :param refresh_interval: 刷新间隔（秒）
        """
        self.room_manager = room_manager
        self.refresh_interval = refresh_interval
        self._thread = None
        self._stop_event = threading.Event()
        self._live = None

    def _build_table(self) -> Table:
        """构建状态表格"""
        now = datetime.now(CHINA_TZ).strftime('%Y-%m-%d %H:%M:%S')

        table = Table(
            title=f"抖音直播监控平台 | 运行中 | {now}",
            title_style="bold cyan",
            border_style="bright_black",
            show_lines=False,
        )

        table.add_column("主播", style="bold", min_width=12, max_width=20, no_wrap=True)
        table.add_column("live_id", min_width=13, max_width=15, no_wrap=True)
        table.add_column("监控状态", justify="center", min_width=8)
        table.add_column("直播", justify="center", min_width=6)
        table.add_column("在线", justify="right", min_width=6)
        table.add_column("收入", justify="right", min_width=8)
        table.add_column("备注", max_width=24, no_wrap=True)

        # 获取所有房间状态
        display_rows = self._get_display_data()

        if not display_rows:
            table.add_row(
                Text("暂无监控房间", style="dim italic"),
                "", "", "", "", "", ""
            )
            return table

        for row in display_rows:
            status = row.get('status', 'stopped')
            style = STATUS_STYLES.get(status, 'dim')
            status_label = STATUS_LABELS.get(status, status)
            live_label = LIVE_STATUS_LABELS.get(status, '未知')

            # 在线人数
            viewer_count = row.get('current_user_count', 0)
            if status == 'monitoring' and viewer_count > 0:
                viewer_str = f"{viewer_count:,}"
            else:
                viewer_str = "-"

            # 收入
            total_income = row.get('total_income', 0)
            if total_income > 0:
                income_str = f"{total_income:,.0f}"
            else:
                income_str = "-"

            # 备注（错误信息等）
            note = row.get('note', '')

            table.add_row(
                Text(row.get('anchor_name', '未知'), style=style),
                Text(row.get('live_id', ''), style="dim"),
                Text(status_label, style=style),
                Text(live_label, style="green" if status == 'monitoring' else "dim"),
                Text(viewer_str, style=style),
                Text(income_str, style=style),
                Text(note, style="yellow" if note else "dim"),
            )

        return table

    def _get_display_data(self) -> list:
        """获取所有房间的显示数据"""
        rows = []
        try:
            data_service = self.room_manager.data_service

            # 获取数据库中所有房间
            all_rooms = data_service.list_live_rooms()

            for room in all_rooms:
                live_id = room.live_id
                row = {
                    'anchor_name': room.anchor_name or live_id,
                    'live_id': live_id,
                    'status': room.status or 'stopped',
                    'current_user_count': 0,
                    'total_income': 0,
                    'note': '',
                }

                # 如果房间在活跃列表中，获取实时统计
                monitored = self.room_manager.active_rooms.get(live_id)
                if monitored:
                    row['current_user_count'] = monitored.stats.get('current_user_count', 0)
                    row['total_income'] = monitored.stats.get('total_income', 0)

                # 错误信息
                if room.status == 'error' and room.error_message:
                    row['note'] = room.error_message[:24]
                elif room.status in ('offline', 'waiting') and room.error_message:
                    row['note'] = room.error_message[:24]

                rows.append(row)
        except Exception:
            pass

        return rows

    def _run(self):
        """后台线程：使用 rich.Live 刷新状态表"""
        try:
            with Live(
                self._build_table(),
                console=console,
                refresh_per_second=0.5,
                transient=False,
            ) as live:
                self._live = live
                while not self._stop_event.is_set():
                    live.update(self._build_table())
                    self._stop_event.wait(self.refresh_interval)
                self._live = None
        except Exception:
            self._live = None

    def start(self):
        """启动状态面板"""
        if self._thread and self._thread.is_alive():
            return

        # 将共享 Console 注册到日志模块，
        # 使 WARNING/ERROR 日志通过 console.print() 输出（渲染在面板上方）
        from utils.logger import set_console
        set_console(console)

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="status-display")
        self._thread.start()

    def stop(self):
        """停止状态面板"""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None
