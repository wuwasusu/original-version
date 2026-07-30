import socket
import json

TCP_HOST = "192.168.1.110"
TCP_PORT = 8080
TEST_API_KEY = "b1221483-748d-4ae2-9024-3cc8e2d68c0c"
TEST_SENSOR_ID = "sensor_001"  # 实际的传感器ID
# -------------------------------------------------------------------

# 创建TCP客户端，连接TCP服务
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client_socket:
    try:
        # 1. 连接TCP服务
        client_socket.connect((TCP_HOST, TCP_PORT))
        print(f"✅ 成功连接TCP服务：{TCP_HOST}:{TCP_PORT}")

        # 2. 构造要发送的数据（示例：先测心跳上报，再测数据上传）
        # 选择1：测试“传感器心跳上报”
        heartbeat_data = {
            "command": "sensor_heartbeat",  # 与TCP服务约定的指令
            "sensor_id": TEST_SENSOR_ID
        }
        # 选择2：测试“油污厚度数据上传”（测完心跳可换这个）
        # upload_data = {
        #     "command": "upload_oil_data",
        #     "sensor_id": TEST_SENSOR_ID,
        #     "thickness": 8.5,  # 符合0-100范围的测试值
        #     "collect_time": "2025-11-29 15:00:00"
        # }

        # 3. 发送JSON数据（转成字符串+UTF-8编码）
        send_data = json.dumps(heartbeat_data, ensure_ascii=False)
        client_socket.sendall(send_data.encode("utf-8"))
        print(f"📤 已发送数据：{send_data}")

        # 4. 接收TCP服务返回的后端响应
        response = client_socket.recv(1024).decode("utf-8")
        response_json = json.loads(response)
        print(f"📥 收到响应：{response_json}")

        # 5. 验证是否成功（根据后端响应判断）
        if response_json["code"] == 200:
            print("🎉 自测成功！TCP服务和后端接口均正常")
        else:
            print(f"❌ 自测失败：{response_json['msg']}")

    except Exception as e:
        print(f"❌ 连接/发送失败：{str(e)}")