import requests
import time
import json
import hmac
import hashlib
import base64
from datetime import datetime
from urllib.parse import quote
import sys

# ==================== 配置信息 ====================
PRODUCT_ID = "J98WW955aG"
DEVICE_NAME = "air"

# 您的 AccessKey（从 OneNET 控制台获取）
ACCESS_KEY = "46dc3120e72a468499184cfdfe4c2ac4"

# 用户ID（从您成功的 token 中解析得到：userid/478772）
USER_ID = "478772"

# API 地址
API_URL = "https://iot-api.heclouds.com/thingmodel/query-device-property"

# Token 有效期（秒）- 设置为24小时
TOKEN_EXPIRY = 24 * 3600

# 数据抓取间隔（秒）
FETCH_INTERVAL = 5

# 调试模式（设为 True 可看到详细调试信息）
DEBUG_MODE = False


# ==================== 配置结束 ====================

def generate_token():
    """
    生成 OneNET 鉴权 token
    使用 HMAC-SHA1 签名算法
    """
    try:
        # Token 版本
        version = "2022-05-01"

        # 资源：用户级别
        resource = f"userid/{USER_ID}"

        # 过期时间（当前时间 + 有效期）
        current_timestamp = int(time.time())
        et = current_timestamp + TOKEN_EXPIRY

        # 签名方法
        method = "sha1"

        # 构建待签名字符串（格式：et\nmethod\nresource\nversion）
        to_sign = f"{et}\n{method}\n{resource}\n{version}"

        if DEBUG_MODE:
            print(f"[调试] 待签名字符串: {to_sign}")
            print(f"[调试] 过期时间: {datetime.fromtimestamp(et).strftime('%Y-%m-%d %H:%M:%S')}")

        # 解码 AccessKey（base64）
        key_bytes = base64.b64decode(ACCESS_KEY)

        # 使用 HMAC-SHA1 签名
        signature_bytes = hmac.new(key_bytes, to_sign.encode('utf-8'), hashlib.sha1).digest()

        # Base64 编码签名
        sign = base64.b64encode(signature_bytes).decode('utf-8')

        # 构建最终 token（需要对特殊字符进行 URL 编码）
        token = f"version={version}&res={quote(resource)}&et={et}&method={method}&sign={quote(sign)}"

        if DEBUG_MODE:
            print(f"[调试] 生成的 token: {token[:100]}...")

        return token

    except Exception as e:
        print(f"❌ Token 生成失败: {e}")
        return None


def fetch_device_data(token):
    """
    使用 token 抓取设备最新数据
    """
    headers = {
        "Accept": "application/json, text/plain, */*",
        "authorization": token,
    }

    params = {
        "product_id": PRODUCT_ID,
        "device_name": DEVICE_NAME
    }

    try:
        response = requests.get(API_URL, headers=headers, params=params, timeout=10)

        if DEBUG_MODE:
            print(f"[调试] HTTP状态码: {response.status_code}")

        if response.status_code == 200:
            result = response.json()

            if result.get('code') == 0:
                return result.get('data', [])
            else:
                error_msg = result.get('msg', '未知错误')
                print(f"❌ API错误: {error_msg}")
                return None
        else:
            print(f"❌ HTTP错误: {response.status_code}")
            if response.status_code == 401:
                print("   认证失败，可能是 AccessKey 不正确")
            return None

    except requests.exceptions.Timeout:
        print("❌ 请求超时")
        return None
    except requests.exceptions.ConnectionError:
        print("❌ 网络连接失败")
        return None
    except Exception as e:
        print(f"❌ 请求失败: {e}")
        return None


def display_data(properties):
    """
    显示设备数据
    """
    if not properties:
        return

    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    print(f"\n{'=' * 60}")
    print(f"📊 设备数据 - {current_time}")
    print(f"{'=' * 60}")

    # 提取重要的传感器数据
    sensor_data = {}
    for prop in properties:
        identifier = prop.get('identifier')
        name = prop.get('name')
        value = prop.get('value')
        timestamp = prop.get('time')

        if value is not None:
            sensor_data[name] = {
                'value': value,
                'time': timestamp,
                'identifier': identifier
            }

    # 按顺序显示数据
    # 优先显示温湿度等关键数据
    priority = ['当前温度', '当前湿度', '电池电量', '信号强度']

    for key in priority:
        if key in sensor_data:
            data = sensor_data[key]
            if data['time']:
                time_str = datetime.fromtimestamp(data['time'] / 1000).strftime('%H:%M:%S')
                print(f"  🌡️ {key:10} : {data['value']:>8}  [{time_str}]")
            else:
                print(f"  🌡️ {key:10} : {data['value']:>8}")
            del sensor_data[key]

    # 显示其他数据
    for name, data in sensor_data.items():
        if data['time']:
            time_str = datetime.fromtimestamp(data['time'] / 1000).strftime('%H:%M:%S')
            print(f"     {name:10} : {data['value']:>8}  [{time_str}]")
        else:
            print(f"     {name:10} : {data['value']:>8}")


def main():
    """主程序：自动管理 token 并实时抓取数据"""
    print("=" * 60)
    print("🤖 OneNET 设备数据实时监控系统")
    print("   自动鉴权版本")
    print("=" * 60)
    print(f"📱 产品ID: {PRODUCT_ID}")
    print(f"🔧 设备名称: {DEVICE_NAME}")
    print(f"👤 用户ID: {USER_ID}")
    print(f"⏱️  Token有效期: {TOKEN_EXPIRY // 3600} 小时")
    print(f"🔄 数据抓取间隔: {FETCH_INTERVAL} 秒")
    print("=" * 60)

    # 测试 AccessKey 解码
    try:
        test_decode = base64.b64decode(ACCESS_KEY)
        print(f"✅ AccessKey 解码成功 (长度: {len(test_decode)} 字节)")
    except Exception as e:
        print(f"❌ AccessKey 解码失败: {e}")
        print("   请检查 ACCESS_KEY 是否正确")
        sys.exit(1)

    # 生成初始 token
    print("\n🔐 正在生成鉴权 Token...")
    current_token = generate_token()

    if current_token is None:
        print("❌ Token 生成失败，程序退出")
        sys.exit(1)

    # 计算 token 过期时间
    token_expire_time = time.time() + TOKEN_EXPIRY
    print(f"✅ Token 生成成功")
    print(f"   过期时间: {datetime.fromtimestamp(token_expire_time).strftime('%Y-%m-%d %H:%M:%S')}")

    # 测试连接
    print("\n🔗 测试连接...")
    test_data = fetch_device_data(current_token)

    if test_data is None:
        print("❌ 连接测试失败！")
        print("\n请检查:")
        print("1. USER_ID 是否正确（应该是 478772）")
        print("2. ACCESS_KEY 是否正确")
        print("3. PRODUCT_ID 和 DEVICE_NAME 是否存在")
        sys.exit(1)

    print("✅ 连接成功！开始实时监控...")
    display_data(test_data)

    # 主循环
    print(f"\n🔄 开始实时监控，每 {FETCH_INTERVAL} 秒刷新一次...")
    print("   按 Ctrl+C 停止程序\n")

    try:
        while True:
            # 检查 token 是否即将过期（提前 5 分钟刷新）
            if time.time() > token_expire_time - 300:
                print("\n⚠️ Token 即将过期，正在刷新...")
                current_token = generate_token()
                if current_token:
                    token_expire_time = time.time() + TOKEN_EXPIRY
                    print(
                        f"✅ Token 刷新成功，新过期时间: {datetime.fromtimestamp(token_expire_time).strftime('%H:%M:%S')}")
                else:
                    print("❌ Token 刷新失败，继续使用旧 token")

            # 抓取数据
            data = fetch_device_data(current_token)

            if data:
                display_data(data)
            else:
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 抓取失败，等待下次重试...")

            # 等待下次抓取
            time.sleep(FETCH_INTERVAL)

    except KeyboardInterrupt:
        print("\n\n✅ 程序已停止")


if __name__ == "__main__":
    main()