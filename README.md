通过修改 hadis898/stock_monitor 进行二次更改

# 介绍
独角数卡 发卡价格库存监控 Python 脚本，主要用于对监测同行的发卡库存情况与价格变动，通过telegram bot进行通知提醒，便于及时掌握商品库和价格变动。

# 支持类型
万能监测，对所有网站都有效，不管你监测什么内容，只要更改关键词 匹配正则表达式就行。

# 部署说明
python版本
1. 安装依赖: pip install requests [如果pip安装报错，解决方法](https://www.upx8.com/4545)
2. 在 MONITOR_URLS 中添加要监控的商品链接和名称
3. 替换 TELEGRAM_BOT_TOKEN 和 TELEGRAM_CHAT_ID
4. 运行命令: sudo python3 stock_monitor.py

# 参数配置

```
CHECK_INTERVAL = 180  # 检查间隔（秒）
STOCK_PATTERN = r'库存\((\d+)\)'  # 匹配库存的正则表达式
PRICE_PATTERN = r'价格\s*(\d+\.\d+)'  # 匹配价格的正则表达式
MAX_WORKERS = 5  # 并发线程数
```

<img width="368" height="183" alt="image" src="https://github.com/user-attachments/assets/1e29c86c-af91-4236-ae96-b1b7c6d1faf4" />


更新：
2025-8-14
1、商品页面改为按钮样式，点击跳转商品页
2、商品更新显示全部商品信息
