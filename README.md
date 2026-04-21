# 新闻推送分析项目

这是一个参考 `TrendRadar` 工作流做的轻量版项目，重点保留了最实用的能力：

- 从 RSS / Atom 源抓取新闻
- 支持 `keyword` 和 `ai` 两种筛选方式
- 使用 OpenAI 兼容接口做 AI 兴趣筛选和摘要分析
- 发送到企业微信机器人
- 自动去重，避免重复推送
- 支持 GitHub Actions 定时运行，电脑关机也能执行

## 当前兼容的 TrendRadar 风格配置

当前版本已经兼容以下配置段：

- `app.timezone`
- `rss.freshness_filter`
- `rss.feeds`
- `report.max_news_per_keyword`
- `filter.method`
- `ai_filter.batch_size`
- `ai_filter.batch_interval`
- `ai_filter.min_score`
- `ai_filter.interests_file`
- `ai.*`
- `ai_analysis.enabled`
- `ai_analysis.language`
- `ai_analysis.max_news_for_analysis`
- `notification.channels.wework.webhook_url`
- `notification.channels.wework.msg_type`
- `storage.local.data_dir`

还没有实现的部分：

- `platforms` 热榜平台抓取
- `schedule` 时间线调度
- 多通知渠道
- TrendRadar 全量模板体系

如果你的目标是“新闻分析后自动发到企业微信”，现在这版已经可以直接用。

## 安装

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 配置

默认配置文件是 [config.yaml](D:/codex/新闻发送/config.yaml)。

### 本地环境变量

项目启动时会自动读取本地的 [\.env](D:/codex/新闻发送/.env)。

你主要需要改这几个值：

```env
WECOM_WEBHOOK=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=你的key
AI_API_KEY=你的模型key
AI_API_BASE=https://api.openai.com/v1
```

如果你使用 DeepSeek：

```env
AI_API_BASE=https://api.deepseek.com
```

然后在 [config.yaml](D:/codex/新闻发送/config.yaml) 里保留模型名，例如：

```yaml
ai:
  model: "deepseek/deepseek-chat"
```

### 兴趣词与关键词

AI 模式默认读取 [config/ai_interests.txt](D:/codex/新闻发送/config/ai_interests.txt)。

关键词模式默认读取 [config/frequency_words.txt](D:/codex/新闻发送/config/frequency_words.txt)。

## 本地运行

先预览消息：

```powershell
python main.py --print-only
```

只跑流程不发消息：

```powershell
python main.py --dry-run
```

正式推送到企业微信：

```powershell
python main.py
```

循环运行，每 30 分钟一轮：

```powershell
python main.py --loop-minutes 30
```

## GitHub Actions 定时推送

已经内置工作流文件：[.github/workflows/daily-news-push.yml](D:/codex/新闻发送/.github/workflows/daily-news-push.yml)

它会在每天北京时间上午 9:00 自动执行一次。

说明：

- GitHub Actions 的 `cron` 使用 UTC
- 北京时间早上 9 点 = UTC 01:00
- 所以工作流里配置的是 `0 1 * * *`

### 你需要做的事

1. 把这个项目推到 GitHub 仓库
2. 在仓库里打开 `Settings` → `Secrets and variables` → `Actions`
3. 新增这些 `Repository secrets`

必填：

- `WECOM_WEBHOOK`
- `AI_API_KEY`

可选：

- `AI_API_BASE`

如果你用 OpenAI 兼容默认地址，可以不填 `AI_API_BASE`，因为 [config.yaml](D:/codex/新闻发送/config.yaml) 里已经有默认值。

### 手动测试

推上 GitHub 后，你可以到仓库的 `Actions` 页面，手动运行 `Daily News Push`，确认企业微信能正常收到消息。

## 配置建议

- 如果你要复用 TrendRadar 的配置，优先保留 `rss`、`filter`、`ai_filter`、`ai`、`ai_analysis`、`notification.channels.wework`
- 如果你只是想做行业监控，先把 RSS 源和兴趣词配准，效果比堆太多功能更稳定
- `ai_filter.min_score` 建议从 `0.6` 到 `0.75` 之间试

## 安全提醒

- 不要把真实的 API key 和企业微信 webhook 提交到仓库里
- 本地开发用 [\.env](D:/codex/新闻发送/.env)
- GitHub 上用 `Secrets`
- 如果密钥已经泄露，建议立刻去服务商后台重新生成
