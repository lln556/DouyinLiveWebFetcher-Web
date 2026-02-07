/**
 * 首页 - 房间列表页面逻辑
 */
const app = new Vue({
    el: '#app',
    data: {
        loading: true,
        showAddModal: false,
        showProxyModal: false,
        showEditModal: false,
        newRoom: {
            live_id: ''
        },
        editRoom: {
            live_id: '',
            anchor_name: '',
            status: ''
        },
        rooms: [],
        stats: {
            total_rooms: 0,
            monitoring_rooms: 0,
            stopped_rooms: 0
        },
        proxy: {
            enabled: false,
            host: '127.0.0.1',
            port: 7890,
            type: 'http'
        },
        error: null
    },
    mounted() {
        this.loadRooms();
        this.loadStats();
        this.loadProxyConfig();
        // 定时刷新状态
        setInterval(() => {
            this.loadRooms();
            this.loadStats();
        }, 5000);
    },
    methods: {
        async loadRooms() {
            try {
                const response = await fetch('/api/rooms');
                const data = await response.json();
                if (data.rooms) {
                    this.rooms = data.rooms;
                }
            } catch (error) {
                console.error('加载房间列表失败:', error);
            }
        },
        async loadStats() {
            try {
                const response = await fetch('/api/rooms/stats/summary');
                const data = await response.json();
                this.stats = data;
            } catch (error) {
                console.error('加载统计数据失败:', error);
            }
        },
        async loadProxyConfig() {
            try {
                const response = await fetch('/api/proxy');
                const data = await response.json();
                this.proxy = data;
            } catch (error) {
                console.error('加载代理配置失败:', error);
            }
        },
        openAddModal() {
            this.showAddModal = true;
            this.newRoom = {
                live_id: ''
            };
        },
        closeAddModal() {
            this.showAddModal = false;
        },
        openProxyModal() {
            this.showProxyModal = true;
        },
        closeProxyModal() {
            this.showProxyModal = false;
        },
        openEditModal(room) {
            this.showEditModal = true;
            this.editRoom = {
                live_id: room.live_id,
                anchor_name: room.anchor_name,
                status: room.status
            };
        },
        closeEditModal() {
            this.showEditModal = false;
        },
        async updateProxyConfig() {
            try {
                const response = await fetch('/api/proxy', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(this.proxy)
                });
                const data = await response.json();

                if (response.ok) {
                    this.proxy = data;
                    this.closeProxyModal();
                    alert('代理配置已更新，重启监控后生效');
                } else {
                    alert(data.error || '更新失败');
                }
            } catch (error) {
                alert('更新失败: ' + error.message);
            }
        },
        async addRoom() {
            if (!this.newRoom.live_id) {
                alert('请输入直播间ID');
                return;
            }

            try {
                const response = await fetch('/api/rooms', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(this.newRoom)
                });
                const data = await response.json();

                if (response.ok) {
                    this.closeAddModal();
                    this.loadRooms();
                    this.loadStats();
                } else {
                    alert(data.error || '添加失败');
                }
            } catch (error) {
                alert('添加失败: ' + error.message);
            }
        },
        async startRoom(liveId) {
            try {
                const response = await fetch(`/api/rooms/${liveId}/start`, {
                    method: 'POST'
                });
                const data = await response.json();

                if (response.ok) {
                    this.loadRooms();
                } else {
                    alert(data.error || '启动失败');
                }
            } catch (error) {
                alert('启动失败: ' + error.message);
            }
        },
        async stopRoom(liveId) {
            if (!confirm('确定要停止监控吗？')) return;

            try {
                const response = await fetch(`/api/rooms/${liveId}/stop`, {
                    method: 'POST'
                });
                const data = await response.json();

                if (response.ok) {
                    this.loadRooms();
                } else {
                    alert(data.error || '停止失败');
                }
            } catch (error) {
                alert('停止失败: ' + error.message);
            }
        },
        async deleteRoom(liveId) {
            if (!confirm('确定要删除此房间吗？此操作不可恢复！')) return;

            try {
                const response = await fetch(`/api/rooms/${liveId}`, {
                    method: 'DELETE'
                });
                const data = await response.json();

                if (response.ok) {
                    this.loadRooms();
                    this.loadStats();
                } else {
                    alert(data.error || '删除失败');
                }
            } catch (error) {
                alert('删除失败: ' + error.message);
            }
        },
        goToRoom(liveId) {
            window.location.href = `/room/${liveId}`;
        },
        getStatusClass(status) {
            // 兼容旧版，使用 monitor_status
            return this.getMonitorStatusClass(status);
        },
        getStatusText(status) {
            // 兼容旧版，使用 monitor_status
            return this.getMonitorStatusText(status);
        },
        getMonitorStatusClass(room) {
            // 基于 status 字段判断监控状态
            switch (room.status) {
                case 'monitoring': return 'bg-green-100 text-green-800';
                case 'offline': return 'bg-yellow-100 text-yellow-800';
                case 'stopped': return 'bg-gray-100 text-gray-800';
                case 'error': return 'bg-red-100 text-red-800';
                default: return 'bg-gray-100 text-gray-800';
            }
        },
        getMonitorStatusText(room) {
            // 基于 status 字段判断监控状态
            switch (room.status) {
                case 'monitoring': return '监控中';
                case 'offline': return '等待中';
                case 'stopped': return '已停止';
                case 'error': return '错误';
                default: return '未知';
            }
        },
        getIsMonitoring(room) {
            // 判断是否正在监控：监控线程运行中
            return room.is_monitor_alive === true;
        },
        getLiveStatusClass(status) {
            switch (status) {
                case 'live': return 'bg-green-100 text-green-800';
                case 'offline': return 'bg-gray-100 text-gray-800';
                default: return 'bg-gray-100 text-gray-800';
            }
        },
        getLiveStatusText(status) {
            switch (status) {
                case 'live': return '直播中';
                case 'offline': return '离线';
                default: return '未知';
            }
        },
        formatIncome(value) {
            return value ? value.toLocaleString() + ' 钻石' : '0 钻石';
        }
    }
});
