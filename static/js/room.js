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
        loadingMessages: true,  // 加载消息时的loading状态
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
        socket: null,
        initialMessageCount: 0,  // 记录初始加载的消息数量
        isAtBottom: true,  // 用户是否在底部
        unreadCount: 0,  // 未读消息数量
        isUserScrolling: false  // 用户是否正在手动滚动
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

        // 并行加载数据
        this.loadRoomInfo();
        this.loadCurrentSession();
        this.loadSessionMessages();  // 加载当前场次消息
        this.loadSessionContributors();
        this.initSocket();

        // 添加滚动监听
        this.$nextTick(() => {
            const container = document.querySelector('.messages-container');
            if (container) {
                container.addEventListener('scroll', this.handleScroll);
            }
        });

        console.log('=== Vue mounted 结束 ===');
    },
    beforeDestroy() {
        if (this.socket) {
            this.socket.disconnect();
        }
        // 移除滚动监听
        const container = document.querySelector('.messages-container');
        if (container) {
            container.removeEventListener('scroll', this.handleScroll);
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
        async loadSessionMessages() {
            this.loadingMessages = true;
            try {
                // 获取当前直播场次
                const sessionResponse = await fetch(`/api/rooms/${this.liveId}/current-session`);
                const sessionData = await sessionResponse.json();

                if (!sessionData.session) {
                    console.log('暂无直播场次数据');
                    this.loadingMessages = false;
                    return;
                }

                const sessionId = sessionData.session.id;
                console.log('加载当前场次消息:', sessionId);

                // 获取当前场次的所有消息（无限制）
                const batchSize = 500;
                let offset = 0;
                let hasMore = true;
                let allMessages = [];

                // 并行加载弹幕和礼物
                const [chatResponse, giftResponse] = await Promise.all([
                    fetch(`/api/sessions/${sessionId}?type=chat&limit=10000`),
                    fetch(`/api/sessions/${sessionId}?type=gift&limit=10000`)
                ]);

                const [chatData, giftData] = await Promise.all([
                    chatResponse.json(),
                    giftResponse.json()
                ]);

                // 合并弹幕消息
                if (chatData.chats) {
                    allMessages.push(...chatData.chats.map(msg => ({
                        type: 'chat',
                        content: msg.display_content || msg.content,
                        timestamp: new Date(msg.created_at)
                    })));
                }

                // 合并礼物消息
                if (giftData.gifts) {
                    allMessages.push(...giftData.gifts.map(msg => ({
                        type: 'gift',
                        content: msg.display_content || `${msg.user_name} 赠送了 ${msg.gift_name} x${msg.gift_count}`,
                        timestamp: new Date(msg.created_at)
                    })));
                }

                // 按时间排序
                allMessages.sort((a, b) => a.timestamp - b.timestamp);

                this.messages = allMessages;
                this.initialMessageCount = allMessages.length;
                console.log(`已加载 ${allMessages.length} 条消息`);

                // 滚动到底部显示最新消息
                this.$nextTick(() => {
                    const container = document.querySelector('.messages-container');
                    if (container) {
                        container.scrollTop = container.scrollHeight;
                        this.isAtBottom = true;
                        this.unreadCount = 0;
                    }
                });
            } catch (error) {
                console.error('加载场次消息失败:', error);
            } finally {
                this.loadingMessages = false;
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
            // 添加到消息列表（新消息在末尾）
            this.messages.push({
                ...data,
                timestamp: new Date()
            });

            // 智能滚动：只有当用户在底部时才自动滚动
            this.$nextTick(() => {
                const container = document.querySelector('.messages-container');
                if (container) {
                    if (this.isAtBottom) {
                        container.scrollTop = container.scrollHeight;
                    } else {
                        this.unreadCount++;
                    }
                }
            });
        },
        handleScroll() {
            const container = document.querySelector('.messages-container');
            if (!container) return;

            const threshold = 50;  // 距离底部50px内视为在底部
            const isBottom = container.scrollHeight - container.scrollTop - container.clientHeight < threshold;

            if (isBottom !== this.isAtBottom) {
                this.isAtBottom = isBottom;
                if (isBottom) {
                    this.unreadCount = 0;  // 滚动到底部时清空未读数
                }
            }
        },
        scrollToBottom() {
            const container = document.querySelector('.messages-container');
            if (container) {
                container.scrollTop = container.scrollHeight;
                this.isAtBottom = true;
                this.unreadCount = 0;
            }
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
