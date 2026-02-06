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
        maxMessages: Infinity,  // 不限制消息数量
        // 历史记录分页相关
        history: {
            messages: [],
            loading: false,
            type: 'all',  // all/chat/gift
            pagination: {
                total: 0,
                page: 1,
                page_size: 50,
                total_pages: 1
            },
            counts: {
                total_count: 0,
                chat_count: 0,
                gift_count: 0
            }
        }
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
        this.loadSessionContributors();  // 首次加载贡献榜
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
        async loadSessionContributors() {
            // 首次加载当前场次贡献榜，避免等待 Socket.IO 推送
            try {
                const response = await fetch(`/api/rooms/${this.liveId}/session-contributors?limit=100`);
                const data = await response.json();

                if (data.contributors && data.contributors.length > 0) {
                    // 转换格式为 stats.contributorInfo 需要的格式
                    this.stats.contributorInfo = data.contributors.map((c, index) => ({
                        rank: index + 1,
                        user: c.nickname || c.user_id,
                        score: c.contribution_value,
                        avatar: c.user_avatar
                    }));
                    this.stats.contributorCount = data.contributors.length;
                }
            } catch (error) {
                console.error('加载场次贡献榜失败:', error);
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
                // 实时更新监控状态
                if (data.room_status && this.room) {
                    this.room.status = data.room_status;
                }

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
        },
        // 历史记录相关方法
        openHistoryModal() {
            this.showHistoryModal = true;
            this.history.page = 1;
            this.history.type = 'all';
            this.loadHistoryData();
        },
        closeHistoryModal() {
            this.showHistoryModal = false;
        },
        async loadHistoryData() {
            this.history.loading = true;
            try {
                const params = new URLSearchParams({
                    page: this.history.pagination.page,
                    limit: this.history.pagination.page_size,
                    type: this.history.type
                });
                const response = await fetch(`/api/rooms/${this.liveId}/messages?${params}`);
                const data = await response.json();

                if (data.messages) {
                    this.history.messages = data.messages;
                }
                if (data.pagination) {
                    this.history.pagination = data.pagination;
                }
                if (data.counts) {
                    this.history.counts = data.counts;
                }
            } catch (error) {
                console.error('加载历史消息失败:', error);
            } finally {
                this.history.loading = false;
            }
        },
        changeHistoryType(type) {
            this.history.type = type;
            this.history.pagination.page = 1;
            this.loadHistoryData();
        },
        goToPage(page) {
            if (page < 1 || page > this.history.pagination.total_pages) return;
            this.history.pagination.page = page;
            this.loadHistoryData();
        },
        prevPage() {
            this.goToPage(this.history.pagination.page - 1);
        },
        nextPage() {
            this.goToPage(this.history.pagination.page + 1);
        },
        formatHistoryMessage(msg) {
            if (msg.type === 'gift') {
                return `${msg.user_name} 赠送了 ${msg.gift_name} x${msg.gift_count}`;
            } else if (msg.content) {
                return msg.content;
            } else if (msg.display_content) {
                return msg.display_content;
            }
            return '';
        },
        getHistoryMessageClass(msg) {
            return msg.type === 'gift' ? 'gift-message' : 'chat-message';
        },
        // 计算分页显示的页码范围
        getPageNumbers() {
            const current = this.history.pagination.page;
            const total = this.history.pagination.total_pages;
            const pages = [];

            if (total <= 7) {
                for (let i = 1; i <= total; i++) {
                    pages.push(i);
                }
            } else {
                if (current <= 4) {
                    for (let i = 1; i <= 5; i++) pages.push(i);
                    pages.push('...');
                    pages.push(total);
                } else if (current >= total - 3) {
                    pages.push(1);
                    pages.push('...');
                    for (let i = total - 4; i <= total; i++) pages.push(i);
                } else {
                    pages.push(1);
                    pages.push('...');
                    for (let i = current - 1; i <= current + 1; i++) pages.push(i);
                    pages.push('...');
                    pages.push(total);
                }
            }
            return pages;
        }
    }
});
