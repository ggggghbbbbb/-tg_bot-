#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import re
import time
import logging
import traceback
import argparse
import os
import sys
import subprocess
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, List, Dict

# 检查并自动安装依赖
def check_and_install_dependencies():
    try:
        import requests
    except ImportError:
        print("正在安装 requests 依赖...")
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'requests'])
        print("requests 依赖安装成功！")

check_and_install_dependencies()

# Telegram Bot 配置
TELEGRAM_BOT_TOKEN = 'bot-token'  # 替换为您的电报 Token
TELEGRAM_CHAT_ID = 'CHAT_ID'  # 替换为您的电报聊天ID

# 监控配置
MONITOR_URLS = [
    {'url': 'https://fk.o808o.com/buy/5', 'name': '小黑子注册码'},
    {'url': 'https://fk.o808o.com/buy/6', 'name': '小黑子续费码'},
]
CHECK_INTERVAL = 10  # 检查间隔（秒）
STOCK_PATTERN = r'库存\((\d+)\)'  # 根据你网站实际内容 匹配库存的正则表达式
# ***** THIS LINE HAS BEEN UPDATED to match your HTML snippet *****
PRICE_PATTERN = r'<span class="price-num">([0-9.]+)</span>' #根据你网站实际内容 匹配价格的正则表达式
MAX_WORKERS = 6  # 并发线程数

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler('stock_monitor.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

class StockMonitor:
    def __init__(self, telegram_bot_token: str, telegram_chat_id: str):
        self.bot_token = telegram_bot_token
        self.chat_id = telegram_chat_id
        self.stock_states: Dict[str, Optional[int]] = {}
        self.price_states: Dict[str, Optional[float]] = {}
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        })

    def get_current_stock_and_price(self, url: str, product_name: str) -> Optional[Dict[str, any]]:
        """
        获取当前商品库存数量和价格，并附带URL和名称
        """
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()

            stock_match = re.search(STOCK_PATTERN, response.text)
            price_match = re.search(PRICE_PATTERN, response.text)

            # Both stock and price must be found for the data to be valid
            if stock_match and price_match:
                stock = int(stock_match.group(1))
                price = float(price_match.group(1))
                logging.info(f"{product_name} -> 库存: {stock}, 价格: ¥{price}")
                return {'stock': stock, 'price': price, 'name': product_name, 'url': url}
            else:
                warnings = []
                if not stock_match:
                    warnings.append("未找到库存信息")
                if not price_match:
                    warnings.append("未找到价格信息")
                logging.warning(f"{product_name} -> {' 且 '.join(warnings)}")
                # Return partial data if stock is found, so we can still monitor stock changes
                if stock_match:
                    stock = int(stock_match.group(1))
                    logging.info(f"{product_name} -> 库存: {stock} (价格未找到)")
                    return {'stock': stock, 'price': 0.0, 'name': product_name, 'url': url} # Use a placeholder for price
                return None

        except (requests.RequestException, ValueError) as e:
            logging.error(f"{product_name} -> 获取页面失败: {e}")
            return None

    def send_telegram_message(self, message: str, keyboard: List[List[Dict]]):
        """
        发送带内联键盘按钮的Telegram消息
        """
        try:
            url = f'https://api.telegram.org/bot{self.bot_token}/sendMessage'
            reply_markup = {'inline_keyboard': keyboard}
            params = {
                'chat_id': self.chat_id,
                'text': message,
                'reply_markup': json.dumps(reply_markup)
            }
            response = requests.post(url, data=params, timeout=10)
            if response.status_code != 200:
                 logging.error(f"发送Telegram通知失败: Status {response.status_code} - {response.text}")
            else:
                logging.info(f"Telegram通知发送成功")
        except requests.RequestException as e:
            logging.error(f"发送Telegram通知失败: {e}")

    def check_stock_changes(self, monitored_urls: List[Dict[str, str]]):
        """
        并发检查所有URL的库存和价格，并在任何一个发生变化时，发送包含所有商品状态的通知。
        """
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = [executor.submit(self.get_current_stock_and_price, item['url'], item['name']) for item in monitored_urls]
            
            current_results = []
            for future in as_completed(futures):
                try:
                    result = future.result()
                    if result:
                        current_results.append(result)
                except Exception as e:
                    logging.error(f"检查过程中发生子线程异常: {e}")

        if not current_results:
            logging.warning("所有商品均未成功获取信息，跳过本次检查。")
            return

        is_first_run = not self.stock_states
        has_changed = False

        if is_first_run:
            logging.info("首次运行，正在初始化商品状态...")
            for item in current_results:
                self.stock_states[item['url']] = item['stock']
                self.price_states[item['url']] = item['price']
                logging.info(f" -> {item['name']} 初始价格: ¥{item['price']}, 初始库存: {item['stock']}")
            return # 首次运行不发送通知

        # 检查是否有任何变化
        for item in current_results:
            url = item['url']
            previous_stock = self.stock_states.get(url)
            previous_price = self.price_states.get(url)
            
            # If item was not tracked before, it's a change
            if previous_stock is None or previous_price is None:
                has_changed = True
                break

            current_stock = item['stock']
            current_price = item['price']

            if previous_stock != current_stock or previous_price != current_price:
                has_changed = True
                break # 发现一个变化就足够触发通知

        if has_changed:
            logging.info("检测到商品信息变化，准备发送通知...")
            # 构建消息和按钮
            message_title = "坤哥发现又有新货上架了，速速来看！！！"
            keyboard = []
            for item in sorted(current_results, key=lambda x: x['name']): # Sort for consistent order
                price_text = f"¥{item['price']}" if item['price'] > 0 else "未知"
                button_text = f"{item['name']}|库存{item['stock']}|价格：{price_text}"
                button = [{'text': button_text, 'url': item['url']}]
                keyboard.append(button)
            
            self.send_telegram_message(message_title, keyboard)

            # 发送通知后，更新所有商品的状态
            for item in current_results:
                self.stock_states[item['url']] = item['stock']
                self.price_states[item['url']] = item['price']
        else:
            logging.info("所有商品状态未发生变化。")

    def monitor(self, monitored_urls: List[Dict[str, str]]):
        """
        持续监控商品库存和价格变化，增加异常处理
        """
        logging.info(f"开始监控 {len(monitored_urls)} 个商品的库存变化")
        # 首次运行时先初始化状态
        self.check_stock_changes(monitored_urls)
        time.sleep(CHECK_INTERVAL)

        while True:
            try:
                self.check_stock_changes(monitored_urls)
                time.sleep(CHECK_INTERVAL)
            except Exception as e:
                error_info = f"监控主循环发生异常:\n{traceback.format_exc()}"
                logging.error(error_info)
                time.sleep(CHECK_INTERVAL)

def setup_systemd():
    """设置 Systemd 服务以实现自动启动。"""
    service_file_content = f"""
[Unit]
Description=Stock Monitor Service
After=network.target

[Service]
ExecStart={sys.executable} {os.path.abspath(__file__)} --run
WorkingDirectory={os.path.dirname(os.path.abspath(__file__))}
StandardOutput=inherit
StandardError=inherit
Restart=always
RestartSec=30s
StartLimitIntervalSec=0

[Install]
WantedBy=multi-user.target
"""
    service_path = '/etc/systemd/system/stock_monitor.service'
    try:
        with open(service_path, 'w') as service_file:
            service_file.write(service_file_content)
        
        os.system('sudo systemctl daemon-reload')
        os.system('sudo systemctl enable stock_monitor.service')
        os.system('sudo systemctl start stock_monitor.service')
        
        print("\033[32m√已经设置并启动了 Stock Monitor 的 Systemd 服务\033[0m")
    except PermissionError:
        print("\033[31m错误: 创建 Systemd 服务文件需要 root 权限。请使用 'sudo python3 your_script.py' 运行此选项。\033[0m")
    except Exception as e:
        print(f"\033[31m设置 Systemd 服务时发生错误: {e}\033[0m")

def check_systemd_status():
    """检查 Systemd 服务的状态"""
    os.system('sudo systemctl status stock_monitor.service')

def check_systemd_restart():
    """重启 Systemd 服务。"""
    os.system('sudo systemctl restart stock_monitor.service')
    print("\033[32m√已成功加载配置，并重启成功\033[0m")
    
def remove_systemd_service():
    """移除 Systemd 服务配置。"""
    os.system('sudo systemctl stop stock_monitor.service')
    os.system('sudo systemctl disable stock_monitor.service')
    os.system('sudo rm /etc/systemd/system/stock_monitor.service')
    os.system('sudo systemctl daemon-reload')
    print("\033[32m√已移除 Stock Monitor 的 Systemd 服务配置\033[0m")

def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='Stock Monitor Service')
    parser.add_argument('--run', action='store_true', help='Run the stock monitor directly')
    return parser.parse_args()

def main():
    args = parse_arguments()
    
    if args.run:
        monitor = StockMonitor(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
        monitor.monitor(MONITOR_URLS)
    else:
        while True:
            print("\033[34m\n输入数字选择：\033[0m")
            print("1、临时运行 -测试效果")
            print("2、后台运行 -自动配置并启动 Systemd 服务")
            print("3、检查 Systemd 状态")
            print("4、重启 Systemd 服务")
            print("5、移除 Systemd 配置")
            print("0、退出")
            
            try:
                choice = input("请选择操作（0-5）：")
                if choice == '1':
                    monitor = StockMonitor(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
                    try:
                        monitor.monitor(MONITOR_URLS)
                    except KeyboardInterrupt:
                        logging.info("\n程序被手动终止")
                        break
                elif choice == '2':
                    setup_systemd()
                elif choice == '3':
                    check_systemd_status()
                elif choice == '4':
                    check_systemd_restart()
                elif choice == '5':
                    remove_systemd_service()
                elif choice == '0':
                    print("\033[31m√成功退出程序\033[0m")
                    break
                else:
                    print("无效的选择，请输入0-5之间的数字。")
            except ValueError:
                print("请输入有效的数字。")
            except Exception as e:
                logging.error(f"操作中发生错误: {e}")
                break

if __name__ == '__main__':
    main()
