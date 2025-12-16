from prometheus_client import Counter, Gauge, Histogram, Info

app_info = Info('vk_channelify', 'VK Channelify bot information')
app_info.info({'version': '1.0.0', 'description': 'VK to Telegram channel reposter'})

# Repost worker metrics
repost_iterations_total = Counter(
    'vk_channelify_repost_iterations_total',
    'Total number of repost worker iterations'
)
repost_iteration_duration_seconds = Histogram(
    'vk_channelify_repost_iteration_duration_seconds',
    'Duration of repost worker iterations in seconds',
    buckets=(1, 5, 10, 30, 60, 120, 300, 600)
)
repost_posts_sent_total = Counter(
    'vk_channelify_posts_sent_total',
    'Total number of posts sent to Telegram channels',
    ['channel_id', 'vk_group_id']
)
repost_errors_total = Counter(
    'vk_channelify_repost_errors_total',
    'Total number of errors during reposting',
    ['error_type', 'channel_id', 'vk_group_id']
)
vk_api_requests_total = Counter(
    'vk_channelify_vk_api_requests_total',
    'Total number of VK API requests',
    ['method', 'status', 'vk_group_id']
)
telegram_api_requests_total = Counter(
    'vk_channelify_telegram_api_requests_total',
    'Total number of Telegram API requests',
    ['method', 'status', 'channel_id', 'vk_group_id']
)
channels_disabled_total = Counter(
    'vk_channelify_channels_disabled_total',
    'Total number of channels disabled',
    ['channel_id', 'vk_group_id']
)

# Channel state metrics
active_channels_gauge = Gauge(
    'vk_channelify_active_channels',
    'Current number of active channels'
)
disabled_channels_gauge = Gauge(
    'vk_channelify_disabled_channels',
    'Current number of disabled channels'
)

# Manage worker metrics
telegram_commands_total = Counter(
    'vk_channelify_telegram_commands_total',
    'Total number of Telegram commands received',
    ['command']
)
telegram_command_duration_seconds = Histogram(
    'vk_channelify_telegram_command_duration_seconds',
    'Duration of Telegram command processing in seconds',
    ['command'],
    buckets=(0.01, 0.05, 0.1, 0.5, 1, 2, 5, 10)
)
telegram_conversations_total = Counter(
    'vk_channelify_telegram_conversations_total',
    'Total number of Telegram conversations',
    ['type', 'status']
)
