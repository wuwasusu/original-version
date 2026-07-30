import uuid
import pymysql

# 数据库连接配置
DB_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': 'Mysql@123456',
    'database': 'oil_sensor',
    'charset': 'utf8mb4'
}

# 生成并插入API Key（替换为实际传感器ID列表）
sensor_ids = ["sensor_001", "sensor_002","sensor_003"]  # 实际传感器ID
conn = pymysql.connect(**DB_CONFIG)
try:
    with conn.cursor() as cur:
        for sensor_id in sensor_ids:
            api_key = str(uuid.uuid4())
            sql = "INSERT INTO sensor_api_keys (sensor_id, api_key) VALUES (%s, %s)"
            cur.execute(sql, (sensor_id, api_key))
            print(f"已为传感器 {sensor_id} 生成 API Key：{api_key}")
        conn.commit()
finally:
    pass