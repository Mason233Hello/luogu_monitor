import websocket
import json
import threading
import time
import requests
from urllib.parse import quote
from datetime import datetime
import logging
import os
import sys

# 尝试导入 win10toast，如果失败则使用备用方案
try:
    from win10toast import ToastNotifier
    TOAST_AVAILABLE = True
except ImportError:
    TOAST_AVAILABLE = False
    print("警告: 未找到 win10toast 库，将使用备用通知方式")

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("luogu_monitor.log"),
        logging.StreamHandler()
    ]
)

class LuoguWebSocketClient:
    def __init__(self, client_id, uid):
        self.cookies = {
            '__client_id': client_id,
            '_uid': uid
        }
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36 Edg/137.0.0.0',
            'Origin': 'https://www.luogu.com.cn',
            'Referer': 'https://www.luogu.com.cn/chat'
        }
        self.ws = None
        self.connected = False
        self.user_id = uid
        self.heartbeat_interval = 20  # 缩短心跳间隔到20秒
        self.reconnect_interval = 60  # 60秒自动重新连接
        self.force_reconnect_interval = 600  # 10分钟强制重新连接
        self.seen_messages = set()
        self.last_message_time = time.time()
        self.last_force_reconnect_time = time.time()
        self.heartbeat_thread = None
        self.reconnect_thread = None
        self.force_reconnect_thread = None
        self.stop_flag = threading.Event()
        
        # 初始化通知器
        if TOAST_AVAILABLE:
            self.toaster = ToastNotifier()
        else:
            self.toaster = None
    
    def show_notification(self, title, message):
        """显示Windows通知"""
        try:
            if TOAST_AVAILABLE and self.toaster:
                # 使用 win10toast 显示通知
                self.toaster.show_toast(
                    title,
                    message,
                    duration=10,
                    icon_path=self.get_icon_path(),
                    threaded=True
                )
                logging.info("已发送通知: %s - %s", title, message)
            else:
                # 备用通知方案
                self.fallback_notification(title, message)
                
        except Exception as e:
            logging.error("发送通知失败: %s", e)
            # 尝试使用备用方案
            self.fallback_notification(title, message)
    
    def get_icon_path(self):
        """获取图标路径"""
        try:
            # 尝试下载洛谷图标
            icon_path = "luogu_icon.ico"
            if not os.path.exists(icon_path):
                response = requests.get("https://www.luogu.com.cn/favicon.ico", timeout=10)
                if response.status_code == 200:
                    with open(icon_path, "wb") as f:
                        f.write(response.content)
                    return icon_path
            return icon_path
        except:
            # 如果下载失败，返回 None
            return None
    
    def fallback_notification(self, title, message):
        """备用通知方案"""
        try:
            # 使用系统弹窗作为备选方案
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, message, title, 0x40)
            logging.info("已发送备用通知: %s - %s", title, message)
        except Exception as e:
            logging.error("备用通知也失败: %s", e)
            # 最后的手段：在控制台打印消息
            print(f"新消息: {title} - {message}")
    
    def on_message(self, ws, message):
        """处理接收到的WebSocket消息"""
        try:
            self.last_message_time = time.time()  # 更新最后收到消息的时间
            
            data = json.loads(message)
            logging.debug("收到消息: %s", json.dumps(data, ensure_ascii=False))
            
            # 根据JavaScript代码的逻辑处理消息
            if (data.get('_ws_type') == 'server_broadcast' and 
                isinstance(data.get('message'), dict)):
                
                message_data = data.get('message', {})
                sender_info = message_data.get('sender', {})
                sender_uid = sender_info.get('uid', '')
                
                # 关键修复：只处理不是自己发送的消息
                # 将发送者UID转换为字符串进行比较，确保类型一致
                if str(sender_uid) != str(self.user_id):
                    sender_name = sender_info.get('name', '未知用户')
                    content = message_data.get('content', '')
                    
                    # 检查是否已经处理过这条消息
                    message_id = message_data.get('id')
                    if message_id and message_id in self.seen_messages:
                        logging.debug("已处理过消息 %s，跳过", message_id)
                        return
                    
                    if message_id:
                        self.seen_messages.add(message_id)
                    
                    logging.info("收到来自 %s (UID: %s) 的私信: %s", sender_name, sender_uid, content)
                    
                    # 发送通知
                    notification_msg = f"{sender_name}: {content}"
                    self.show_notification("洛谷新消息", notification_msg)
                else:
                    # 记录自己发送的消息，但不通知
                    logging.debug("忽略自己发送的消息: %s", message_data.get('content', ''))
                
        except json.JSONDecodeError:
            logging.error("无法解析的消息: %s", message)
        except Exception as e:
            logging.error("处理消息时出错: %s", e)
    
    def on_error(self, ws, error):
        """处理WebSocket错误"""
        logging.error("WebSocket错误: %s", error)
        self.connected = False
        self.schedule_reconnect()
    
    def on_close(self, ws, close_status_code, close_msg):
        """处理WebSocket关闭"""
        logging.info("WebSocket连接关闭，代码: %s, 消息: %s", close_status_code, close_msg)
        self.connected = False
        self.schedule_reconnect()
    
    def on_open(self, ws):
        """WebSocket连接建立时的回调"""
        logging.info("WebSocket连接已建立")
        self.connected = True
        self.last_message_time = time.time()
        
        # 根据JavaScript代码发送加入频道消息
        join_message = {
            "type": "join_channel",
            "channel": "chat",
            "channel_param": self.user_id,
            "exclusive_key": None
        }
        self.ws.send(json.dumps(join_message))
        logging.info("已发送加入频道消息")
        
        # 启动心跳线程
        self.start_heartbeat()
        
        # 启动重连检查线程
        self.start_reconnect_check()
        
        # 启动强制重连线程
        self.start_force_reconnect()
    
    def connect(self):
        """建立WebSocket连接"""
        # 使用JavaScript代码中的固定WebSocket URL
        ws_url = "wss://ws.luogu.com.cn/ws"
        
        logging.info("连接至: %s", ws_url)
        
        # 创建WebSocket连接
        self.ws = websocket.WebSocketApp(
            ws_url,
            header=[f"{k}: {v}" for k, v in self.headers.items()],
            cookie=f"__client_id={self.cookies['__client_id']}; _uid={self.cookies['_uid']}",
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
            on_open=self.on_open
        )
        
        # 运行WebSocket客户端
        self.ws.run_forever()
    
    def send_heartbeat(self):
        """发送心跳包"""
        if not self.connected:
            return
            
        # 根据JavaScript代码，可能需要发送心跳包
        # 如果需要，可以添加类似以下代码：
        # heartbeat_msg = {"type": "heartbeat"}
        # self.ws.send(json.dumps(heartbeat_msg))
        # logging.debug("已发送心跳")
        pass
    
    def start_heartbeat(self):
        """启动心跳线程"""
        if self.heartbeat_thread and self.heartbeat_thread.is_alive():
            return
            
        def heartbeat_loop():
            while self.connected and not self.stop_flag.is_set():
                try:
                    self.send_heartbeat()
                except Exception as e:
                    logging.error("发送心跳失败: %s", e)
                time.sleep(self.heartbeat_interval)
                
        self.heartbeat_thread = threading.Thread(target=heartbeat_loop)
        self.heartbeat_thread.daemon = True
        self.heartbeat_thread.start()
        logging.info("心跳线程已启动，间隔: %s秒", self.heartbeat_interval)
    
    def start_reconnect_check(self):
        """启动重连检查线程"""
        if self.reconnect_thread and self.reconnect_thread.is_alive():
            return
            
        def reconnect_check_loop():
            while not self.stop_flag.is_set():
                # 检查是否需要重连
                if self.connected and time.time() - self.last_message_time > self.reconnect_interval:
                    logging.warning("超过 %s 秒未收到消息，主动重连", self.reconnect_interval)
                    self.disconnect()
                    self.schedule_reconnect()
                
                time.sleep(10)  # 每10秒检查一次
                
        self.reconnect_thread = threading.Thread(target=reconnect_check_loop)
        self.reconnect_thread.daemon = True
        self.reconnect_thread.start()
        logging.info("重连检查线程已启动，检查间隔: 10秒")
    
    def start_force_reconnect(self):
        """启动强制重连线程"""
        if self.force_reconnect_thread and self.force_reconnect_thread.is_alive():
            return
            
        def force_reconnect_loop():
            while not self.stop_flag.is_set():
                # 检查是否需要强制重连
                if time.time() - self.last_force_reconnect_time > self.force_reconnect_interval:
                    logging.warning("达到 %s 秒强制重连时间，重新连接所有链接", self.force_reconnect_interval)
                    self.last_force_reconnect_time = time.time()
                    self.disconnect()
                    self.schedule_reconnect()
                
                time.sleep(30)  # 每30秒检查一次
                
        self.force_reconnect_thread = threading.Thread(target=force_reconnect_loop)
        self.force_reconnect_thread.daemon = True
        self.force_reconnect_thread.start()
        logging.info("强制重连线程已启动，检查间隔: 30秒")
    
    def disconnect(self):
        """断开WebSocket连接"""
        if self.ws:
            try:
                self.ws.close()
            except:
                pass
        self.connected = False
    
    def schedule_reconnect(self):
        """安排重新连接"""
        if self.stop_flag.is_set():
            return
            
        logging.info("将在 5 秒后尝试重新连接...")
        time.sleep(5)
        
        if not self.stop_flag.is_set():
            try:
                self.connect()
            except Exception as e:
                logging.error("重新连接失败: %s", e)
                # 如果重连失败，再次安排重连
                self.schedule_reconnect()
    
    def run(self):
        """运行WebSocket客户端"""
        logging.info("启动洛谷私信监控...")
        logging.info("按 Ctrl+C 停止")
        
        # 显示启动通知
        self.show_notification("洛谷监控", "洛谷私信监控已启动")
        
        try:
            self.connect()
        except KeyboardInterrupt:
            self.stop()
        except Exception as e:
            logging.error("运行出错: %s", e)
            self.stop()
    
    def stop(self):
        """停止监控"""
        logging.info("停止监控...")
        self.stop_flag.set()
        self.disconnect()
        # 显示停止通知
        self.show_notification("洛谷监控", "洛谷私信监控已停止")

if __name__ == "__main__":
    # 从用户获取cookie信息
    client_id = input("请输入 __client_id: ")
    uid = input("请输入 _uid: ")
    
    # 创建WebSocket客户端并运行
    client = LuoguWebSocketClient(client_id, uid)
    
    try:
        client.run()
    except Exception as e:
        logging.error("程序运行出错: %s", e)
        input("按回车键退出...")