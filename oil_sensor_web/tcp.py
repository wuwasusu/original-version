import json
import requests
from datetime import datetime

# 1. 核心配置
TCP_HOST = '0.0.0.0'
TCP_PORT = 8080
BUFFER_SIZE = 1024
BACKEND_BASE_URL = 'http://192.168.1.108:5000'
REQUIRED_API_KEY = 'b5a43424-f7ae-4ea7-ad69-978fcd37e946'
SUPPORTED_COMMANDS = ['sensor_heartbeat', 'upload_oil_data']

# 2. 工具函数（对接后端接口）
def call_backend_api(api_path, method, headers=None, json_data=None):
    """调用后端接口，返回接口响应字典"""
    url = f"{BACKEND_BASE_URL}{api_path}"
    try:
        if method == 'POST':
            response = requests.post(url, headers=headers, json=json_data, timeout=5)
        elif method == 'GET':
            response = requests.get(url, headers=headers, params=json_data, timeout=5)
        else:
            return {"code": 400, "msg": "不支持的请求方法", "data": {}}

        # 检查响应是否为空
        if not response.text:
            return {"code": 500, "msg": "后端返回空响应", "data": {}}

        # 尝试解析 JSON，捕获解析错误
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
