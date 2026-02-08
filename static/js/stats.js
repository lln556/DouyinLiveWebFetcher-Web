/**
 * 直播数据统计页面逻辑
 */
const app = new Vue({
    el: '#app',
    data: {
        rooms: [],
        selectedRoomId: '',
        timeRange: '7days',
        customStartDate: '',
        customEndDate: '',
        minDate: '',  // 可选的最早日期
        maxDate: '',  // 可选的最晚日期
        stats: {},
        sessions: [],
        contributors: [],  // 贡献榜
        contributorPagination: {  // 贡献榜分页
            page: 1,
            page_size: 20,
            total: 0,
            total_pages: 1
        },
        loading: true,
        hasSearched: false,
        // 场次详情相关
        showSessionModal: false,
        sessionDetail: {},
        sessionDetailLoading: false,
        sessionDetailTab: 'chats',
        sessionDetailChats: [],
        sessionDetailGifts: [],
        sessionDetailContributors: [],
        // 场次详情分页
        sessionDetailPagination: {
            chats: { page: 1, page_size: 50, total: 0, total_pages: 1 },
            gifts: { page: 1, page_size: 50, total: 0, total_pages: 1 }
        },
        sessionDetailCounts: { chat_count: 0, gift_count: 0 },
        // 用户消息模态框
        showUserMessagesModal: false,
        userMessagesLoading: false,
        userMessagesTab: 'all',
        userMessagesData: {
            user: {},
            stats: {
                total_messages: 0,
                chat_count: 0,
                gift_count: 0,
                total_value: 0
            },
            messages: [],
            pagination: {
                page: 1,
                page_size: 50,
                total: 0,
                total_pages: 1
            }
        },
        userMessagesQuery: {
            user_id: null,
            live_id: null,
            session_id: null,
            start_date: null,
            end_date: null
        }
    },
    async mounted() {
        await Promise.all([
            this.loadRooms(),
            this.loadDateRange()
        ]);
        this.initCustomDates();
        // 不在 mounted 时自动加载数据，等待用户点击查询
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
        async loadDateRange() {
            // 加载所有房间的日期范围
            try {
                const response = await fetch('/api/rooms/date-range');
                const data = await response.json();
                if (data.min_date) {
                    this.minDate = data.min_date;
                }
                if (data.max_date) {
                    this.maxDate = data.max_date;
                }
            } catch (error) {
                console.error('加载日期范围失败:', error);
            }
        },
        initCustomDates() {
            // 初始化自定义日期为最近7天，但要在允许的范围内
            const today = new Date();
            let weekAgo = new Date(today);
            weekAgo.setDate(weekAgo.getDate() - 7);

            // 如果有日期限制，调整到允许的范围内
            if (this.minDate) {
                const minDt = new Date(this.minDate);
                if (weekAgo < minDt) {
                    weekAgo = new Date(minDt);
                }
            }

            this.customEndDate = this.formatDateForInput(today);
            this.customStartDate = this.formatDateForInput(weekAgo);
        },
        onTimeRangeChange() {
            if (this.timeRange !== 'custom') {
                this.loadData();
            }
        },
        getDateRange() {
            const today = new Date();
            let startDate, endDate;

            switch (this.timeRange) {
                case '7days':
                    startDate = new Date(today);
                    startDate.setDate(startDate.getDate() - 7);
                    startDate.setHours(0, 0, 0, 0);
                    endDate = new Date();
                    break;
                case '30days':
                    startDate = new Date(today);
                    startDate.setDate(startDate.getDate() - 30);
                    startDate.setHours(0, 0, 0, 0);
                    endDate = new Date();
                    break;
                case 'custom':
                    if (!this.customStartDate || !this.customEndDate) {
                        return null;
                    }
                    startDate = new Date(this.customStartDate + 'T00:00:00');
                    endDate = new Date(this.customEndDate + 'T23:59:59');
                    break;
                default:
                    startDate = new Date(today);
                    startDate.setDate(startDate.getDate() - 7);
                    startDate.setHours(0, 0, 0, 0);
                    endDate = new Date();
            }

            // 使用本地时区的日期字符串，避免时区转换问题
            const formatDate = (date) => {
                const year = date.getFullYear();
                const month = String(date.getMonth() + 1).padStart(2, '0');
                const day = String(date.getDate()).padStart(2, '0');
                return `${year}-${month}-${day}`;
            };

            return {
                start: formatDate(startDate),
                end: formatDate(endDate)
            };
        },
        async loadData() {
            const dateRange = this.getDateRange();
            if (!dateRange) {
                alert('请选择自定义日期范围');
                return;
            }

            const params = new URLSearchParams({
                start_date: dateRange.start.split('T')[0],
                end_date: dateRange.end.split('T')[0]
            });

            try {
                // 加载统计数据
                const statsUrl = this.selectedRoomId
                    ? `/api/rooms/${this.selectedRoomId}/sessions/stats?${params}`
                    : `/api/rooms/sessions/stats?${params}`;

                const statsResponse = await fetch(statsUrl);
                const statsData = await statsResponse.json();
                if (statsData.stats) {
                    this.stats = statsData.stats;
                }

                // 加载贡献榜数据（第一页）
                await this.loadContributors(1);

                // 如果选择了房间，加载场次列表
                if (this.selectedRoomId) {
                    const sessionsUrl = `/api/rooms/${this.selectedRoomId}/sessions?${params}`;
                    const sessionsResponse = await fetch(sessionsUrl);
                    const sessionsData = await sessionsResponse.json();
                    if (sessionsData.sessions) {
                        this.sessions = sessionsData.sessions;
                    }
                } else {
                    this.sessions = [];
                }

                // 标记已查询
                this.hasSearched = true;
            } catch (error) {
                console.error('加载数据失败:', error);
            } finally {
                this.loading = false;
            }
        },
        async loadContributors(page = 1) {
            const dateRange = this.getDateRange();
            if (!dateRange) {
                return;
            }

            const params = new URLSearchParams({
                start_date: dateRange.start.split('T')[0],
                end_date: dateRange.end.split('T')[0],
                page: page,
                page_size: this.contributorPagination.page_size
            });

            if (this.selectedRoomId) {
                params.append('live_id', this.selectedRoomId);
            }

            try {
                const response = await fetch(`/api/rooms/contributors-by-date?${params}`);
                const data = await response.json();

                if (data.contributors) {
                    this.contributors = data.contributors;
                }
                if (data.page) {
                    this.contributorPagination.page = data.page;
                }
                if (data.page_size) {
                    this.contributorPagination.page_size = data.page_size;
                }
                if (data.total) {
                    this.contributorPagination.total = data.total;
                }
                if (data.total_pages) {
                    this.contributorPagination.total_pages = data.total_pages;
                }
            } catch (error) {
                console.error('加载贡献榜失败:', error);
            }
        },
        goToContributorPage(page) {
            if (page < 1 || page > this.contributorPagination.total_pages) return;
            this.loadContributors(page);
        },
        getContributorPageNumbers() {
            const current = this.contributorPagination.page;
            const total = this.contributorPagination.total_pages;
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
        },
        loadRoomData() {
            this.sessions = [];
            this.contributors = [];
            this.contributorPagination = { page: 1, page_size: 20, total: 0, total_pages: 1 };
            this.hasSearched = false;
            // 加载选中房间的日期范围
            this.loadRoomDateRange();
            // 重新初始化自定义日期
            this.initCustomDates();
            // 不自动加载数据，等待用户点击查询
        },
        async loadRoomDateRange() {
            // 加载选中房间的日期范围
            if (this.selectedRoomId) {
                try {
                    const response = await fetch(`/api/rooms/date-range?live_id=${this.selectedRoomId}`);
                    const data = await response.json();
                    if (data.min_date) {
                        this.minDate = data.min_date;
                    }
                    if (data.max_date) {
                        this.maxDate = data.max_date;
                    }
                } catch (error) {
                    console.error('加载房间日期范围失败:', error);
                }
            } else {
                // 加载所有房间的日期范围
                await this.loadDateRange();
            }
        },
        async viewSessionDetail(session) {
            this.showSessionModal = true;
            this.sessionDetail = session;
            this.sessionDetailLoading = true;
            this.sessionDetailTab = 'chats';
            // 重置分页
            this.sessionDetailPagination = {
                chats: { page: 1, page_size: 50, total: 0, total_pages: 1 },
                gifts: { page: 1, page_size: 50, total: 0, total_pages: 1 }
            };

            try {
                // 先获取基本信息和消息总数
                const response = await fetch(`/api/rooms/sessions/${session.id}?type=chat&page=1&limit=50`);
                const data = await response.json();

                if (data.session) {
                    this.sessionDetail = data.session;
                }
                if (data.counts) {
                    this.sessionDetailCounts = data.counts;
                }
                if (data.chats) {
                    this.sessionDetailChats = data.chats;
                }
                if (data.pagination) {
                    this.sessionDetailPagination.chats = data.pagination;
                }

                // 同时获取贡献榜
                const contribResponse = await fetch(`/api/rooms/sessions/${session.id}?type=contributors`);
                const contribData = await contribResponse.json();
                if (contribData.contributors) {
                    this.sessionDetailContributors = contribData.contributors;
                }
            } catch (error) {
                console.error('加载场次详情失败:', error);
            } finally {
                this.sessionDetailLoading = false;
            }
        },
        async loadSessionDetailTab(tab) {
            this.sessionDetailTab = tab;

            if (tab === 'chats' && this.sessionDetailChats.length === 0) {
                await this.loadSessionDetailData('chat');
            } else if (tab === 'gifts' && this.sessionDetailGifts.length === 0) {
                await this.loadSessionDetailData('gift');
            }
        },
        async loadSessionDetailData(type) {
            const pagination = type === 'chat' ? this.sessionDetailPagination.chats : this.sessionDetailPagination.gifts;
            try {
                const response = await fetch(`/api/rooms/sessions/${this.sessionDetail.id}?type=${type}&page=${pagination.page}&limit=${pagination.page_size}`);
                const data = await response.json();

                if (type === 'chat' && data.chats) {
                    this.sessionDetailChats = data.chats;
                    if (data.pagination) {
                        this.sessionDetailPagination.chats = data.pagination;
                    }
                } else if (type === 'gift' && data.gifts) {
                    this.sessionDetailGifts = data.gifts;
                    if (data.pagination) {
                        this.sessionDetailPagination.gifts = data.pagination;
                    }
                }
            } catch (error) {
                console.error(`加载${type === 'chat' ? '弹幕' : '礼物'}记录失败:`, error);
            }
        },
        async goToSessionPage(type, page) {
            const pagination = type === 'chat' ? this.sessionDetailPagination.chats : this.sessionDetailPagination.gifts;
            if (page < 1 || page > pagination.total_pages) return;
            pagination.page = page;
            await this.loadSessionDetailData(type);
        },
        getSessionPageNumbers(type) {
            const pagination = type === 'chat' ? this.sessionDetailPagination.chats : this.sessionDetailPagination.gifts;
            const current = pagination.page;
            const total = pagination.total_pages;
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
        },
        closeSessionModal() {
            this.showSessionModal = false;
            this.sessionDetail = {};
            this.sessionDetailChats = [];
            this.sessionDetailGifts = [];
            this.sessionDetailContributors = [];
            this.sessionDetailPagination = {
                chats: { page: 1, page_size: 50, total: 0, total_pages: 1 },
                gifts: { page: 1, page_size: 50, total: 0, total_pages: 1 }
            };
            this.sessionDetailCounts = { chat_count: 0, gift_count: 0 };
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
        formatAvgIncome() {
            if (!this.stats.total_sessions || this.stats.total_sessions === 0) {
                return '0 钻石';
            }
            const avg = this.stats.total_income / this.stats.total_sessions;
            return avg.toLocaleString(undefined, { maximumFractionDigits: 0 }) + ' 钻石';
        },
        formatDuration(seconds) {
            if (!seconds || seconds === 0) return '0分钟';

            const hours = Math.floor(seconds / 3600);
            const minutes = Math.floor((seconds % 3600) / 60);

            if (hours > 0) {
                return `${hours}小时${minutes}分钟`;
            }
            return `${minutes}分钟`;
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
        formatDateForInput(date) {
            const d = new Date(date);
            const year = d.getFullYear();
            const month = String(d.getMonth() + 1).padStart(2, '0');
            const day = String(d.getDate()).padStart(2, '0');
            return `${year}-${month}-${day}`;
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
        // 用户消息模态框方法
        async openUserMessagesModal(userId, userName, options = {}) {
            this.showUserMessagesModal = true;
            this.userMessagesLoading = true;
            this.userMessagesTab = 'all';

            // 设置查询参数
            this.userMessagesQuery = {
                user_id: userId,
                live_id: options.live_id || this.selectedRoomId,
                session_id: options.session_id || null,
                start_date: options.start_date || null,
                end_date: options.end_date || null
            };

            // 如果没有指定日期范围，使用当前筛选的日期范围
            if (!this.userMessagesQuery.start_date || !this.userMessagesQuery.end_date) {
                const dateRange = this.getDateRange();
                if (dateRange) {
                    this.userMessagesQuery.start_date = dateRange.start;
                    this.userMessagesQuery.end_date = dateRange.end;
                }
            }

            // 重置数据
            this.userMessagesData = {
                user: {
                    user_id: userId,
                    nickname: userName
                },
                stats: {
                    total_messages: 0,
                    chat_count: 0,
                    gift_count: 0,
                    total_value: 0
                },
                messages: [],
                pagination: {
                    page: 1,
                    page_size: 50,
                    total: 0,
                    total_pages: 1
                }
            };

            await this.loadUserMessages();
        },
        closeUserMessagesModal() {
            this.showUserMessagesModal = false;
            this.userMessagesData = {
                user: {},
                stats: {
                    total_messages: 0,
                    chat_count: 0,
                    gift_count: 0,
                    total_value: 0
                },
                messages: [],
                pagination: {
                    page: 1,
                    page_size: 50,
                    total: 0,
                    total_pages: 1
                }
            };
            this.userMessagesQuery = {
                user_id: null,
                live_id: null,
                session_id: null,
                start_date: null,
                end_date: null
            };
        },
        async loadUserMessages() {
            if (!this.userMessagesQuery.user_id || !this.userMessagesQuery.live_id) return;

            this.userMessagesLoading = true;
            try {
                const params = new URLSearchParams({
                    user_id: this.userMessagesQuery.user_id,
                    type: this.userMessagesTab,
                    page: this.userMessagesData.pagination.page,
                    limit: this.userMessagesData.pagination.page_size
                });

                if (this.userMessagesQuery.session_id) {
                    params.append('session_id', this.userMessagesQuery.session_id);
                } else if (this.userMessagesQuery.start_date && this.userMessagesQuery.end_date) {
                    params.append('start_date', this.userMessagesQuery.start_date);
                    params.append('end_date', this.userMessagesQuery.end_date);
                }

                const response = await fetch(`/api/rooms/${this.userMessagesQuery.live_id}/user-messages?${params}`);
                const data = await response.json();

                if (data.user) {
                    this.userMessagesData.user = data.user;
                }
                if (data.stats) {
                    this.userMessagesData.stats = data.stats;
                }
                if (data.messages) {
                    this.userMessagesData.messages = data.messages;
                }
                if (data.pagination) {
                    this.userMessagesData.pagination = data.pagination;
                }
            } catch (error) {
                console.error('加载用户消息失败:', error);
            } finally {
                this.userMessagesLoading = false;
            }
        },
        async switchUserMessagesTab(tab) {
            if (this.userMessagesTab === tab) return;
            this.userMessagesTab = tab;
            this.userMessagesData.pagination.page = 1;
            await this.loadUserMessages();
        },
        async userMessagesGoToPage(page) {
            const pagination = this.userMessagesData.pagination;
            if (page < 1 || page > pagination.total_pages) return;
            pagination.page = page;
            await this.loadUserMessages();
        },
        formatUserMessageTime(dateStr) {
            if (!dateStr) return '';
            const d = new Date(dateStr);
            return d.toLocaleTimeString('zh-CN', {
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit'
            });
        }
    }
});
