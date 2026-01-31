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
        stats: {},
        sessions: [],
        loading: true
    },
    mounted() {
        this.loadRooms();
        this.initCustomDates();
        this.loadData();
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
        initCustomDates() {
            // 初始化自定义日期为最近7天
            const today = new Date();
            const weekAgo = new Date(today);
            weekAgo.setDate(weekAgo.getDate() - 7);

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
                case 'today':
                    startDate = new Date(today);
                    startDate.setHours(0, 0, 0, 0);
                    endDate = new Date();
                    break;
                case 'yesterday':
                    const yesterday = new Date(today);
                    yesterday.setDate(yesterday.getDate() - 1);
                    startDate = new Date(yesterday);
                    startDate.setHours(0, 0, 0, 0);
                    endDate = new Date(yesterday);
                    endDate.setHours(23, 59, 59, 999);
                    break;
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
                case 'thisMonth':
                    startDate = new Date(today.getFullYear(), today.getMonth(), 1);
                    endDate = new Date();
                    break;
                case 'lastMonth':
                    startDate = new Date(today.getFullYear(), today.getMonth() - 1, 1);
                    endDate = new Date(today.getFullYear(), today.getMonth(), 0);
                    endDate.setHours(23, 59, 59, 999);
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
            } catch (error) {
                console.error('加载数据失败:', error);
            } finally {
                this.loading = false;
            }
        },
        loadRoomData() {
            this.sessions = [];
            this.loadData();
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
        }
    }
});
