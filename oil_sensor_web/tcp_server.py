import socket
import json
import requests
from datetime import datetime

# 1. 核心配置
# TCP服务配置（WiFi连接用）
TCP_HOST = '0.0.0.0'  # 监听所有网络接口，确保通信模块可访问
TCP_PORT =6060

BUFFER_SIZE = 1024  # 单次数据接收上限（字节）

# 后端接口配置
BACKEND_BASE_URL = 'http://192.168.1.105:5000'
REQUIRED_API_KEY = '6997034b-bb1f-4be2-a30c-017516990ec6'

# 支持的通信指令（与通信同学约定的对应后端接口）
ALARM_THRESHOLD = 100
SUPPORTED_COMMANDS = ['sensor_heartbeat', 'upload_data']

# 2. 工具函数（对接后端接口）
# def call_backend_api(api_path, method, headers=None, json_data=None):
#     """调用后端接口，返回接口响应字典"""
#     url = f"{BACKEND_BASE_URL}{api_path}"
#     try
#         if method == 'POST':
#             response = requests.post(url, headers=headers, json=json_data, timeout=5)
#         elif method == 'GET':
#
#
#             response = requests.get(url, headers=headers, params=json_data, timeout=5)
#         # 解析后端JSON响应（后端所有接口均返回JSON）
#         return response.json() if response.status_code in [200, 400, 401,404, 500] else {"code": response.status_code,
#                                                                                      "msg": "后端响应格式异常"}
#     except requests.exceptions.RequestException as e:
#         # 后端服务不可达时的错误响应
#         return {"code": 500, "msg": f"后端服务调用失败：{str(e)}", "data": {}}
def call_backend_api(api_path, method, headers=None, json_data=None):
    url = f"{BACKEND_BASE_URL}{api_path}"
    try:
        if method == 'POST':
            response = requests.post(url, headers=headers, json=json_data, timeout=5)
        elif method == 'GET':
            response = requests.get(url, headers=headers, params=json_data, timeout=5)
        else:
            return {"code": 400, "msg": "不支持的请求方法", "data": {}}

        if not response.text:
            return {"code": 500, "msg": "后端返回空响应", "data": {}}

        try:
            if response.status_code in [200, 400, 401, 404, 500]:
                return response.json()
            else:
                return {"code": response.status_code, "msg": "后端响应格式异常", "data": {}}
        except json.JSONDecodeError:
            return {
                "code": 500,
                "msg": f"后端返回非JSON响应: {response.text[:100]}...",
                "data": {"raw_response": response.text[:200]}
            }

    except requests.exceptions.RequestException as e:
        return {"code": 500, "msg": f"后端服务调用失败: {str(e)}", "data": {}}

# 3. TCP服务端核心逻辑
def handle_client_connection(conn, client_addr):
    """处理单个通信模块的连接与数据交互"""
    print(f"[新连接] 通信模块地址：{client_addr}")
    try:
        # 接收通信模块发送的JSON数据
        recv_bytes = conn.recv(BUFFER_SIZE)
        if not recv_bytes:
            print(f"[连接断开] {client_addr}：未接收任何数据")
            return
        # 【新增：打印原始数据，看ESP32到底
        print(f"[原始数据] {client_addr}: {recv_bytes}")  # 打印字节流（能看到特殊字符）
        print(f"[解码后数据] {client_addr}: {recv_bytes.decode('utf-8', errors='replace')}")  # 解码后打印（替换无法识别的字符）
        # 解码并解析JSON数据（通信模块需发送UTF-8编码的JSON）
        recv_json = json.loads(recv_bytes.decode('utf-8'))
        print(f"[接收数据] {client_addr}：{recv_json}")

        # 1. 校验通信指令是否支持
        if 'command' not in recv_json or recv_json['command'] not in SUPPORTED_COMMANDS:
            error_resp = {"code": 400, "msg": f"不支持的指令，仅支持{SUPPORTED_COMMANDS}", "data": {}}
            conn.sendall(json.dumps(error_resp, ensure_ascii=False).encode('utf-8'))
            print(f"[处理失败] {client_addr}：指令错误")
            return

        # 2. 统一设置请求头（含API密钥，传感器接口需校验）
        request_headers = {
            'Content-Type': 'application/json',
            'X-API-Key': REQUIRED_API_KEY
        }

        # 3. 根据指令对接不同后端接口
        command = recv_json['command']
        if command == 'sensor_heartbeat':
            # 对接“传感器心跳上报”接口（POST /sensor_heartbeat）
            backend_resp = call_backend_api(
                api_path='/sensor_heartbeat',
                method='POST',
                headers=request_headers,
                json_data={'sensor_id': recv_json.get('sensor_id')}
            )

        elif command == 'upload_data':
            # 对接“油污厚度数据上传”接口（POST /upload_data）
            # 预处理数据：确保thickness为数字，且符合0-1000范围（提前校验减少后端报错）
            flow_rate = recv_json.get('flow_rate', -1)
            total_liters = recv_json.get('total_liters', -1)
            if (not isinstance(flow_rate, (int, float)) or flow_rate < 0 or flow_rate > 1000) or \
                        (not isinstance(total_liters, (int, float)) or total_liters < 0):
                backend_resp = {"code": 400, "msg": "参数错误：瞬时流量需在0-1000 L/min范围内,累计流量不能为负", "data": {}}
            else:
                if flow_rate > ALARM_THRESHOLD:
                    print(f"[{client_addr}] 流量 {flow_rate} 超过阈值 {ALARM_THRESHOLD}，触发关阀指令！")
                    control_cmd = {
                        "command": "control_valve",
                        "action": "close",
                        "reason": f"flow_rate_exceeded_{ALARM_THRESHOLD}"
                    }
                    conn.sendall(json.dumps(control_cmd, ensure_ascii=False).encode('utf-8'))
                backend_resp = call_backend_api(
                    api_path='/upload_data',
                    method='POST',
                    headers=request_headers,
                    json_data={
                        'sensor_id': recv_json.get('sensor_id'),
                        'flow_rate': flow_rate,
                        'total_liters': total_liters,
                        'collect_time': recv_json.get('collect_time', datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                    }
                )

        # 4. 将后端响应返回给通信模块
        conn.sendall(json.dumps(backend_resp, ensure_ascii=False).encode('utf-8'))
        print(f"[处理成功] {client_addr}: 后端响应已返回 -> {json.dumps(backend_resp, ensure_ascii=False)}")

    except json.JSONDecodeError:
        # 处理JSON格式错误（后端接口要求所有请求为JSON）
        error_resp = {"code": 400, "msg": "数据格式错误：需发送UTF-8编码的JSON", "data": {}}
        conn.sendall(json.dumps(error_resp, ensure_ascii=False).encode('utf-8'))
        print(f"[处理失败] {client_addr}：JSON解析错误")
    except Exception as e:
        # 其他未知错误
        error_resp = {"code": 500, "msg": f"服务处理异常：{str(e)}", "data": {}}
        conn.sendall(json.dumps(error_resp, ensure_ascii=False).encode('utf-8'))
        print(f"[处理异常] {client_addr}：{str(e)}")
    finally:
        conn.close()
        print(f"[连接关闭] {client_addr}\n")


#  4. 启动TCP服务
def start_tcp_server():
    # 创建TCP socket（IPv4 + 流式传输）
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp_server:
        # 允许端口复用（避免服务重启时端口占用报错）
        tcp_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        tcp_server.bind((TCP_HOST, TCP_PORT))
        tcp_server.listen(5)  # 同时支持5个连接（满足多传感器场景）

        # 提示关键信息（需同步给通信同学）
        print("=" * 60)
        print("TCP服务已启动（对接后端传感器接口）")
        print(f"1. WiFi连接信息：后端IP={BACKEND_BASE_URL.split('//')[1].split(':')[0]}, TCP端口={TCP_PORT}")
        print(f"2. 支持指令：{SUPPORTED_COMMANDS}")
        print(f"3. 通信数据格式示例：")
        print(f"   - 心跳上报：{{'command':'sensor_heartbeat', 'sensor_id':'sensor_001'}}")
        print(
            f"   - 数据上传：{{'command':'upload_data', 'sensor_id':'sensor_001', 'flow_rate':58,'total_liters':100, 'collect_time':'2025-11-24 16:30:00'}}")
        print("=" * 60)

        while True:
            # 阻塞等待通信模块连接
            conn, client_addr = tcp_server.accept()
            # 处理连接（单线程：适合测试/低并发；高并发可改用线程池）
            handle_client_connection(conn, client_addr)


#  5. 入口函数
if __name__ == "__main__":
    start_tcp_server()