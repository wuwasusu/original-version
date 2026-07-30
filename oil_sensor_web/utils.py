from logger import logger
import logging
heartbeat_logger = logging.getLogger("sensor_heartbeat")
heartbeat_logger.setLevel(logging.WARNING)
heartbeat_logger.info("传感器心跳接口被调用")  # 此条INFO会被屏蔽，不输出到终端

DB_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': 'Mysql@123456',
    'database': 'oil_sensor',
    'charset': 'utf8mb4'
}

def get_db_connection():
    conn = pymysql.connect(**DB_CONFIG)
    return conn


import functools
from pymysql import OperationalError, ProgrammingError


def handle_api_exceptions(func):
    @functools.wraps(func)  # 保留原函数的名称和文档，便于调试
    def wrapper(*args, **kwargs):
        try:
            # 执行原接口函数（核心业务逻辑）
            return func(*args, **kwargs)

        # 1. 捕获参数错误（主动抛的ValueError）
        except ValueError as ve:
            return jsonify({"code": 400, "msg": f"参数错误：{str(ve)}"}), 400

        # 2. 捕获数据库连接/操作异常
        except OperationalError as oe:
            return jsonify({"code": 500, "msg": f"数据库异常：连接超时或服务未启动（{str(oe)}）"}), 500

        # 3. 捕获SQL语法错误
        except ProgrammingError as pe:
            return jsonify({"code": 500, "msg": f"SQL语法错误：{str(pe)}"}), 500

        # 4. 兜底捕获未知异常
        except Exception as e:
            return jsonify({"code": 500, "msg": f"系统异常：{str(e)}"}), 500

    return wrapper


from functools import wraps
from flask import request, jsonify
import pymysql


def require_api_key(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        # 从请求头获取API Key
        api_key = request.headers.get('X-API-Key')
        if not api_key:
            return jsonify({"code": 401, "msg": "缺少X-API-Key请求头"}), 401

        # 校验API Key有效性
        conn = pymysql.connect(**DB_CONFIG)
        try:
            with conn.cursor() as cur:
                sql = "SELECT sensor_id FROM sensor_api_keys WHERE api_key = %s AND is_active = 1"
                cur.execute(sql, (api_key,))
                result = cur.fetchone()
                if not result:
                    return jsonify({"code": 401, "msg": "无效或已过期的API Key"}), 401
                # 将传感器ID注入请求，便于后续业务逻辑使用
                request.sensor_id = result[0]
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"API Key校验异常：{str(e)}")
            return jsonify({"code": 500, "msg": "服务器错误"}), 500

    return wrapper