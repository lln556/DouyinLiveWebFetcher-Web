/**
 * 房间详情页 - 实时监控页面逻辑
 */
const app = new Vue({
    el: '#app',
    data: {
        liveId: null,
        live_id: null,  // 用于模板显示
        room: null,
        loading: true,
        activeTab: 'all', // all/chat/gift
        messages: [],
        stats: {
            currentUserCount: 0,
            totalUserCount: 0,
            totalIncome: 0,
            contributorCount: 0,
            contributorInfo: []
        },
        currentSession: null,
        contributors: [],
        historyMessages: [],
        showHistoryModal: false,
        socket: null,
        maxMessages: 200
    },
    computed: {
        filteredMessages() {
            if (this.activeTab === 'all') {
                return this.messages;
            } else if (this.activeTab === 'chat') {
                return this.messages.filter(m => m.type === 'chat');
            } else if (this.activeTab === 'gift') {
                return this.messages.filter(m => m.type === 'gift');
            }
            return this.messages;
        }
    },
    mounted() {
        console.log('=== Vue mounted 开始 ===');
        this.liveId = document.querySelector('meta[name="live-id"]').content;
        this.live_id = this.liveId;

        console.log('liveId:', this.liveId);
        console.log('Vue 实例:', this);
        console.log('messages 数组:', this.messages);

        this.loadRoomInfo();
        this.loadCurrentSession();
        this.loadHistoryMessages();
        this.initSocket();
        console.log('=== Vue mounted 结束 ===');
    },
    beforeDestroy() {
        if (this.socket) {
            this.socket.disconnect();
        }
    },
    methods: {
        async loadRoomInfo() {
            try {
                const response = await fetch(`/api/rooms/${this.liveId}`);
                const data = await response.json();

                if (data.room) {
                    this.room = data.room;
                    if (data.room.stats) {
                        this.stats = data.room.stats;
                    }
                    // 更新页面标题
                    const anchorName = data.room.anchor_name || this.liveId;
                    document.title = `${anchorName} - 直播详情`;
                }
            } catch (error) {
                console.error('加载房间信息失败:', error);
            } finally {
                this.loading = false;
            }
        },
        async loadCurrentSession() {
            try {
                const response = await fetch(`/api/rooms/${this.liveId}/current-session`);
                const data = await response.json();
                if (data.session) {
                    this.currentSession = data.session;
                }
            } catch (error) {
                console.error('加载当前直播场次失败:', error);
            }
        },
        async loadHistoryMessages() {
            try {
                const response = await fetch(`/api/rooms/${this.liveId}/messages?limit=50`);
                const data = await response.json();

                if (data.messages) {
                    this.historyMessages = data.messages;
                }
            } catch (error) {
                console.error('加载历史消息失败:', error);
            }
        },
        async startMonitoring() {
            try {
                const response = await fetch(`/api/rooms/${this.liveId}/start`, {
                    method: 'POST'
                });
                const data = await response.json();

                if (response.ok) {
                    this.loadRoomInfo();
                } else {
                    alert(data.error || '启动失败');
                }
            } catch (error) {
                alert('启动失败: ' + error.message);
            }
        },
        async stopMonitoring() {
            if (!confirm('确定要停止监控吗？')) return;

            try {
                const response = await fetch(`/api/rooms/${this.liveId}/stop`, {
                    method: 'POST'
                });
                const data = await response.json();

                if (response.ok) {
                    this.loadRoomInfo();
                } else {
                    alert(data.error || '停止失败');
                }
            } catch (error) {
                alert('停止失败: ' + error.message);
            }
        },
        async loadContributors() {
            try {
                const response = await fetch(`/api/rooms/${this.liveId}/contributors?limit=100`);
                const data = await response.json();

                if (data.contributors) {
                    this.contributors = data.contributors;
                }
            } catch (error) {
                console.error('加载贡献榜失败:', error);
            }
        },
        initSocket() {
            if (this.socket) {
                this.socket.disconnect();
            }

            this.socket = io();

            this.socket.on('connect', () => {
                console.log('Socket.IO连接已建立');
                // 加入房间
                this.socket.emit('join', { live_id: this.liveId });
            });

            this.socket.on('disconnect', () => {
                console.log('Socket.IO连接已断开');
            });

            this.socket.on(`room_${this.liveId}`, (data) => {
                this.handleMessage(data);
            });

            this.socket.on(`room_${this.liveId}_stats`, (data) => {
                this.stats = {
                    currentUserCount: data.current_user_count || 0,
                    totalUserCount: data.total_user_count || 0,
                    totalIncome: data.total_income || 0,
                    contributorCount: data.contributor_count || 0,
                    contributorInfo: data.contributor_info || []
                };

                // 实时更新当前场次数据
                if (data.current_session) {
                    this.currentSession = data.current_session;
                }
            });
        },
        handleMessage(data) {
            console.log('=== 处理消息 ===');
            console.log('消息数据:', data);
            console.log('当前消息数量:', this.messages.length);

            // 添加到消息列表（新消息在末尾）
            this.messages.push({
                ...data,
                timestamp: new Date()
            });

            console.log('添加后消息数量:', this.messages.length);
            console.log('filteredMessages数量:', this.filteredMessages.length);

            // 限制消息数量
            if (this.messages.length > this.maxMessages) {
                this.messages.shift();
            }

            // 滚动到底部查看最新消息
            this.$nextTick(() => {
                const container = document.querySelector('.messages-container');
                if (container) {
                    container.scrollTop = container.scrollHeight;
                    console.log('已滚动到底部');
                }
            });
        },
        setTab(tab) {
            this.activeTab = tab;
        },
        formatIncome(value) {
            return value ? value.toLocaleString() + ' 钻石' : '0 钻石';
        },
        formatNumber(value) {
            if (!value) return '0';
            value = Number(value);
            if (value >= 100000000) {
                return (value / 100000000).toFixed(1) + '亿';
            } else if (value >= 10000) {
                return (value / 10000).toFixed(1) + '万';
            } else {
                return value.toLocaleString();
            }
        },
        formatTime(date) {
            if (!date) return '';
            const d = new Date(date);
            return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        },
        getStatusClass(status) {
            switch (status) {
                case 'monitoring': return 'bg-green-100 text-green-800';
                case 'stopped': return 'bg-gray-100 text-gray-800';
                case 'error': return 'bg-red-100 text-red-800';
                default: return 'bg-gray-100 text-gray-800';
            }
        },
        getStatusText(status) {
            switch (status) {
                case 'monitoring': return '监控中';
                case 'stopped': return '已停止';
                case 'error': return '错误';
                default: return status;
            }
        },
        getMessageClass(message) {
            if (message.type === 'gift') {
                return 'gift-message';
            } else if (message.is_gift_user) {
                return 'gift-user-message';
            }
            return 'chat-message';
        },
        getSessionStatusClass(status) {
            switch (status) {
                case 'live': return 'bg-green-100 text-green-800';
                case 'ended': return 'bg-gray-100 text-gray-800';
                default: return 'bg-gray-100 text-gray-800';
            }
        },
        getSessionStatusText(status) {
            switch (status) {
                case 'live': return '直播中';
                case 'ended': return '已结束';
                default: return status;
            }
        },
        formatDateTime(dateStr) {
            if (!dateStr) return '-';
            const d = new Date(dateStr);
            return d.toLocaleString('zh-CN', {
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit'
            });
        },
        getDuration(startTime, endTime) {
            if (!startTime) return '-';
            const start = new Date(startTime);
            const end = endTime ? new Date(endTime) : new Date();
            const diff = end - start;

            const hours = Math.floor(diff / (1000 * 60 * 60));
            const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));

            if (hours > 0) {
                return `${hours}小时${minutes}分钟`;
            }
            return `${minutes}分钟`;
        },
        getRankClass(rank) {
            if (rank === 1) return 'rank-1';
            if (rank === 2) return 'rank-2';
            if (rank === 3) return 'rank-3';
            return 'rank-other';
        }
    }
});
