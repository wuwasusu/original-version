import logging,xlsxwriter, io, datetime

from flask import send_file,Flask
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash  # 密码加密py
from utils import get_db_connection, handle_api_exceptions, require_api_key
from logger import logger
from flask_cors import CORS  # 导入CORS
heartbeat_logger = logging.getLogger("sensor_heartbeat")
heartbeat_logger.setLevel(logging.WARNING)

heartbeat_logger.info("传感器心跳接口被调用")  # 此条INFO会被屏蔽，不输出到终端

# 正确使用示例
current_datetime = datetime.datetime.now
# #
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('api_logs.log'),  # 日志写入文件
        logging.StreamHandler()  # 同时输出到控制台
    ]
)
logger = logging.getLogger(__name__)

# 创建专门的心跳日志器，与主日志器区分
heartbeat_logger = logging.getLogger("sensor_heartbeat")
heartbeat_logger.setLevel(logging.WARNING)  # 只显示心跳相关的警告/错误

import pymysql
pymysql.install_as_MySQLdb()

# 1. 初始化 Flask 应用
app = Flask(__name__)
# 全局变量：暂存要下发给4G模块的指令（如"calibrate"校准、"stop"停止测量）
latest_cmd = ""
ALARM_THRESHOLD = 100

# 关键配置：会话加密密钥
app.config['SECRET_KEY'] = 'oil_sensor_web_2025_abc123'
# 2. 配置SQLAlchemy
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:Mysql%40123456@localhost:3306/oil_sensor?charset=utf8mb4'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 3. 初始化数据库和登录管理器
db = SQLAlchemy(app)
@app.cli.command()
def create_tables():
    with app.app_context():
        db.create_all()
login_manager = LoginManager(app)
# 未登录用户访问敏感接口时，会重定向到/login路由
login_manager.login_view = 'login'

# 定义用户表模型（对应MySQL中的users表，会自动创建）
class User(UserMixin, db.Model):
    __tablename__ = 'users'  # MySQL中表名是users
    # 字段和表（oil_data、sensor_status）格式对应，用int/varchar等
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)  # 自增ID（和oil_data的id一致）
    username = db.Column(db.VARCHAR(50), unique=True, nullable=False)  # 用户名（唯一，不能重复）
    password_hash = db.Column(db.VARCHAR(200), nullable=False)  # 加密后的密码（存明文不安全）

    # 方法1：给用户设置密码（自动加密）
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)  # 加密存储

    # 方法2：验证密码（输入的明文和数据库加密密码比对）
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)  # 解密验证

# GPS 定位数据模型
class GPSData(db.Model):
    __tablename__ = 'gps_data'
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String(64), nullable=False)  # 设备ID（可复用 sensor_id）
    lon = db.Column(db.Float, nullable=False)              # 经度
    lat = db.Column(db.Float, nullable=False)              # 纬度
    speed = db.Column(db.Float, default=0)                 # 速度(km/h)
    direction = db.Column(db.Integer, default=0)           # 方向(0-359°)
    locate_time = db.Column(db.DateTime)                  # 定位时间
    create_time = db.Column(db.DateTime, default=datetime.datetime.now)  # 入库时间


# 关键回调：登录管理器通过用户ID加载用户（必须写）
@login_manager.user_loader
def load_user(user_id):
    # 从数据库中根据id查询用户（和查oil_data数据逻辑类似）
    return User.query.get(int(user_id))


# 创建users表到MySQL数据库
with app.app_context():
    db.create_all()


    # 接口1：用户登录（POST请求，接收用户名密码）
    @app.route('/login', methods=['POST'])
    @handle_api_exceptions
    def login():
        data = request.get_json()  # 假设前端传JSON格式：{"username":"test","password":"123456"}
        username = data.get('username')
        password = data.get('password')

        # 1. 查数据库中是否有这个用户
        user = User.query.filter_by(username=username).first()

        # 2. 验证密码：用户存在 + 密码正确
        if user and user.check_password(password):
            login_user(user)  # 登录成功，记录用户状态
            return jsonify({
                "code": 200,
                "msg": "登录成功",
                "data": {"username": username}
            })
        # 验证失败
        return jsonify({"code": 400, "msg": "用户名或密码错误", "data": {}})


    # 接口2：用户登出（必须登录才能访问，用@login_required装饰）
    @app.route('/logout', methods=['POST'])
    @login_required  # 敏感接口，未登录会被拦截
    def logout():
        logout_user()  # 清除用户登录状态
        return jsonify({"code": 200, "msg": "登出成功", "data": {}})

# 【报警设备控制接口的路由函数】
@app.route('/control_alarm', methods=['POST'])
@login_required
def control_alarm():
    try:
        # 解析请求参数
        cmd = request.json.get('cmd')
        operator = request.json.get('operator')

        # 校验指令合法性
        if cmd not in ['start', 'stop']:
            return jsonify({"code": 400, "msg": "指令错误，仅支持start/stop"})

        # （可选）对接硬件通信（如MQTT/串口，此处示例为模拟）
        exec_status = "success"  # 假设硬件执行成功

        # 记录操作日志到数据库
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = pymysql.connect(**DB_CONFIG)
        cur = conn.cursor()
        sql = """
              INSERT INTO alarm_control_log (operator, cmd, operate_time, exec_status) VALUES (%s, %s, %s, %s) \
              """
        cur.execute(sql, (operator, cmd, current_time, exec_status))
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({
            "code": 200,
            "msg": "操作成功",
            "data": {"cmd": cmd, "status": exec_status}
        })
    except Exception as e:
        return jsonify({"code": 500, "msg": f"操作失败: {str(e)}"})


# 【传感器参数控制接口的路由函数】
@app.route('/set_sensor_freq', methods=['POST'])
@login_required
@handle_api_exceptions
def set_sensor_freq():
    try:
        # 解析请求参数
        sensor_id = request.json.get('sensor_id')
        sample_freq = request.json.get('sample_freq')
        operator = request.json.get('operator')

        # 校验参数合法性
        if not sensor_id or sample_freq not in [5, 10]:
            return jsonify({"code": 400, "msg": "参数错误，需传入sensor_id和合法频率(5/10)"})

        # 更新数据库传感器状态
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = pymysql.connect(**DB_CONFIG)
        cur = conn.cursor()
        sql_update = """
                     UPDATE sensor_status SET sample_freq = %s, update_time = %s, operator    = %s WHERE sensor_id = %s 
                     """
        cur.execute(sql_update, (sample_freq, current_time, operator, sensor_id))
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({
            "code": 200,
            "msg": "参数更新成功",
            "data": {"sensor_id": sensor_id, "new_freq": sample_freq}
        })
    except Exception as e:
        return jsonify({"code": 500, "msg": f"操作失败: {str(e)}"})

@app.route('/')
def index():
    return '欢迎访问首页'

@app.route('/your_api', methods=['GET'])
def your_api():
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM sensor_status;")
        result = cur.fetchall()
    conn.close()
    return jsonify(result)

# 2. MySQL 配置
app.config['MYSQL_HOST']='localhost'
app.config['MYSQL_PORT']=3306
app.config['MYSQL_USER']='root'
app.config['MYSQL_PASSWORD']='Mysql@123456'
app.config['MYSQL_DB']='oil_sensor'
app.config['MYSQL_CURSORCLASS']='DictCursor'

# 3. 初始化 MySQL 连接
from flask_mysqldb import MySQL
mysql = MySQL(app)

# 4. 数据上传接口（接收厚度数据，存入 MySQL）
@app.route("/upload_data", methods=["POST"])
@handle_api_exceptions
@require_api_key
def upload_data():
    try:
        # 解析前端传的 JSON 数据
        data = request.json
        # 记录调用者IP和请求参数
        client_ip = request.remote_addr
        logger.info(f"接口/upload_data被调用，调用者IP: {client_ip}，请求参数: {data}")
        flow_rate = data.get("flow_rate")
        total_liters = data.get("total_liters")
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # 先从请求体中获取 sensor_id
        sensor_id = data.get('sensor_id')
        # 若 sensor_id 为空，返回参数错误
        if not sensor_id:
            return jsonify({"code": 400, "msg": "sensor_id 为必填参数"}), 400

        # 验证参数（确保厚度是数字）
        if flow_rate is None or not isinstance(flow_rate, (int, float)):
            error_msg = "参数错误: 请传入有效的瞬时流量值(数字)"
            logger.error(f"接口/upload_data参数错误: {error_msg}")
            return jsonify({"code": 400, "msg": "参数错误：请传入有效的瞬时值（数字）"})
        if total_liters is None or not isinstance(flow_rate, (int, float)):
            error_msg = "参数错误: 请传入有效的累计流量值(数字)"
            logger.error(f"接口/upload_data参数错误: {error_msg}")
            return jsonify({"code": 400, "msg": "参数错误：请传入有效的累计流量值（数字）"})

        # 校验厚度范围（0-100mm）
        if not (0 <= flow_rate <= 1000):
            error_msg = "参数错误：瞬时流量值需在 0-1000范围内"
            logger.error(f"接口/upload_data参数错误: {error_msg}")
            return jsonify({"code": 400, "msg": error_msg})

        # 阈值判断：标记是否报警
        is_alarm = flow_rate > ALARM_THRESHOLD  # True为报警，False为正常

        # 5. 插入数据到 MySQL
        cur = mysql.connection.cursor()  # 获取操作游标
        cur.execute("INSERT INTO oil_data (sensor_id, flow_rate,total_liters, collect_time, is_alarm) VALUES (%s, %s,%s, %s, %s)",
                    (sensor_id, flow_rate,total_liters, current_time, is_alarm))
        mysql.connection.commit()  # ！！！必须提交，否则数据不写入数据库！！！
        cur.close()

        response_data = {
            "code": 200,
            "msg": "数据上传成功",
            "data": {
                "flow_rate": flow_rate,
                "total_liters": total_liters,
                "collect_time": current_time,
                "is_alarm": is_alarm,
                "alarm_threshold": ALARM_THRESHOLD
            }
        }
        logger.info(f"接口/upload_data响应结果: {response_data}")
        # 返回成功响应
        return jsonify({
            "code": 200,
            "msg": "数据上传成功",
            "data": {
                "flow_rate":flow_rate,
                "total_liters": total_liters,
                "collect_time": current_time,
                "is_alarm": is_alarm,  # 新增：告知前端是否报警
                "alarm_threshold": ALARM_THRESHOLD  # 新增：返回阈值方便前端展示
            }
        })
    except Exception as e:
        error_msg = f"接口/upload_data调用失败: {str(e)}"
        logger.error(error_msg)
        # 捕获错误并返回（方便排查）
        return jsonify({"code": 500, "msg": f"上传失败：{str(e)}"})


# 5. 历史数据查询接口（根据 start_time 查询指定时间后的数据）
@app.route("/get_history", methods=["GET"])
@handle_api_exceptions
def get_history():
    try:
        # 1. 解析 GET 请求的 URL 参数（获取前端传的 start_time）
        # 从 URL 中提取 start_time，例如：http://127.0.0.1:5000/get_history?start_time=2025-11-12 16:14:40
        start_time = request.args.get("start_time")
        client_ip = request.remote_addr
        logger.info(f"接口/get_history被调用，调用者IP: {client_ip}，请求参数: start_time={start_time}")

        # 2. 验证参数（确保 start_time 不为空，且格式符合预期）
        if not start_time:
            error_msg = "参数错误: 请传入 start_time (格式: YYYY-MM-DD HH:mm:ss)"
            logger.error(f"接口/get_history参数错误: {error_msg}")
            return jsonify({"code": 400, "msg": "参数错误：请传入 start_time（格式：YYYY-MM-DD HH:mm:ss）"})

        # 3. 从 MySQL 中查询数据（筛选 collect_time 大于等于 start_time 的记录）
        cur = mysql.connection.cursor()
        # SQL 语句：查询 oil_data 表中，时间 >= start_time 的所有数据，按时间倒序排列（最新的在前）
        cur.execute(
            "SELECT id, flow_rate,total_liters, collect_time FROM oil_data WHERE collect_time >= %s ORDER BY collect_time DESC",
            (start_time,))
        # 获取查询结果（因配置了 DictCursor，结果是字典列表，方便前端解析）
        history_data = cur.fetchall()
        cur.close()  # 关闭游标

        response_data = {
            "code": 200,
            "msg": "查询成功",
            "total": len(history_data),
            "data": history_data
        }
        logger.info(f"接口/get_history响应结果: {response_data}")
        # 4. 返回查询结果（包含数据总数和具体数据）
        return jsonify({
            "code": 200,
            "msg": "查询成功",
            "total": len(history_data),  # 数据总数（方便前端显示）
            "data": history_data  # 具体的历史数据列表
        })
    except Exception as e:
        error_msg = f"接口/get_history调用失败: {str(e)}"
        logger.error(error_msg)
        # 捕获错误（如 SQL 语法错误、数据库连接问题），返回错误信息
        return jsonify({"code": 500, "msg": f"查询失败：{str(e)}"})
@app.route(rule="/test", methods=["GET"])
def test_route():
        return "test success"


import pymysql
from flask import  request, jsonify
import datetime

# 数据库连接配置（复用已有配置）
DB_CONFIG = {
    'host': app.config['MYSQL_HOST'],
    'user': app.config['MYSQL_USER'],
    'password': app.config['MYSQL_PASSWORD'],
    'database':'oil_sensor',
    'cursorclass': pymysql.cursors.DictCursor
}
# ========== 1. 传感器心跳接收接口 ==========
@app.route('/sensor_heartbeat', methods=['POST'])
@handle_api_exceptions
@require_api_key
def sensor_heartbeat():
    try:
        # 解析心跳包参数（需包含 sensor_id）
        data = request.json
        sensor_id = data.get('sensor_id')
        if not sensor_id:
            return jsonify({"code": 400, "msg": "参数错误：需传入 sensor_id"})

        # 处理 sensor_id 为列表的情况（兼容单个和多个值）
        if not isinstance(sensor_id, list):
            sensor_id = [sensor_id]  # 单个值转为列表，统一处理逻辑

        current_time = datetime.datetime.now()
        conn = pymysql.connect(**DB_CONFIG)
        cur = conn.cursor()

        # 动态构造 IN 语句的占位符（如 sensor_id 有3个值，则生成 %s,%s,%s）
        placeholders = ','.join(['%s'] * len(sensor_id))
        # 检查传感器是否已存在，不存在则新增，存在则更新
        cur.execute(
            f"SELECT * FROM sensor_status WHERE sensor_id IN ({placeholders})",
            tuple(sensor_id)
        )
        if not cur.fetchone():
            # 新增传感器记录（循环插入每个 sensor_id）
            for sid in sensor_id:
                cur.execute(
                    "INSERT INTO sensor_status (sensor_id, online_status, last_heartbeat_time) "
                    "VALUES (%s, 1, %s)",
                    (sid, current_time)
                )
        else:
            # 更新传感器记录（循环更新每个 sensor_id）
            for sid in sensor_id:
                cur.execute(
                    "UPDATE sensor_status SET online_status=1, last_heartbeat_time=%s "
                    "WHERE sensor_id=%s",
                    (current_time, sid)
                )
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({"code": 200, "msg": "心跳包接收成功"})
    except Exception as e:
        logger.error(f"心跳处理异常：{str(e)}")
        return jsonify({"code": 500, "msg": "服务器内部错误"})
@app.route(rule='/get_history_chart_data', methods=['GET'])
@handle_api_exceptions
def get_history_chart_data():
        # 1. 接收前端参数（变量名加前缀）
        chart_start_time = request.args.get('start_time')
        chart_end_time = request.args.get('end_time')
        chart_sensor_id = request.args.get('sensor_id', '')  # 与外部sensor_id区分

        # 2. 数据库查询逻辑（连接和游标变量加前缀）
        chart_conn = pymysql.connect(**DB_CONFIG)
        with chart_conn.cursor() as chart_cur:
            sql = """
                  SELECT collect_time, flow_rate,total_liters, FROM oil_data  WHERE collect_time BETWEEN %s AND %s \
                  """
            chart_params = [chart_start_time, chart_end_time]
            if chart_sensor_id:
                sql += " AND sensor_id = %s "
                chart_params.append(chart_sensor_id)
            sql += " ORDER BY collect_time ASC "
            chart_cur.execute(sql, chart_params)
            chart_results = chart_cur.fetchall()

        # 3. 处理无数据的情况
        if not chart_results:
            return jsonify({
                "code": 400,
                "msg": "暂无数据",
                "data": {"times": [], "flow_rates": [] ,"total_liters": []}
            })

        # 4. 组装数据为前端可用格式
        times = [row['collect_time'].strftime('%Y-%m-%d %H:%M:%S') for row in chart_results]
        flow_rates = [float(row['flow_rate']) for row in chart_results]
        total_liters = [float(row['total_liters']) for row in chart_results]
        # 5. 最终返回结果（确保此处代码可执行）
        return jsonify({
            "code": 200,
            "msg": "查询成功",
            "data": {
            "times": times,
            "flow_rates": flow_rates,
            "total_liters": total_liters},}
             )
@app.route('/export_oil_data_excel', methods=['GET'])
@login_required
@handle_api_exceptions
def export_oil_data_excel():
        start_time = request.args.get('start_time')
        end_time = request.args.get('end_time')
        sensor_id = request.args.get('sensor_id', '')

        # 数据库查询数据
        conn = pymysql.connect(**DB_CONFIG)
        with conn.cursor() as cur:
            sql = """ SELECT id, float_rate,total_liters, collect_time, is_alarm  FROM oil_data WHERE collect_time BETWEEN %s AND %s  """
            params = [start_time, end_time]
            if sensor_id:
                sql += " AND sensor_id = %s"
                params.append(sensor_id)
            sql += " ORDER BY collect_time ASC"
            cur.execute(sql, params)
            results = cur.fetchall()

        # 在内存中创建Excel并写入数据
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet("流量数据")

        # 写入表头
        header = ["数据ID", "瞬时流量(L/min)","累计流量(L)" "采集时间", "是否报警"]
        worksheet.write_row(0, 0, header)
        header_format = workbook.add_format({'bold': True})
        for col, value in enumerate(header):
            worksheet.write(0, col, value, header_format)

        # 写入数据行
        for row_num, row_data in enumerate(results, start=1):
            is_alarm = "是" if row_data['is_alarm'] else "否"
            collect_time = row_data['collect_time'].strftime('%Y-%m-%d %H:%M:%S')
            worksheet.write_row(row_num, 0, [
                row_data['id'],
                row_data['float_rate'],
                row_data['total_liters'],
                collect_time,
                is_alarm
            ])

        workbook.close()
        output.seek(0)

        # 生成带时间戳的文件名并返回
        file_name = f"流量数据导出_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.xlsx"
        return send_file(
            output,
            as_attachment=True,
            download_name=file_name,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

# ========== 2. 传感器状态查询接口（可选，用于验证） ==========
@app.route('/get_sensor_status', methods=['GET'])
def get_sensor_status():
    try:
        sensor_id = request.args.get('sensor_id')  # 可选参数，不传则查询所有
        conn = pymysql.connect(**DB_CONFIG)
        cur = conn.cursor()

        if sensor_id:
            cur.execute("SELECT * FROM sensor_status WHERE sensor_id = %s", (sensor_id,))
            result = cur.fetchone()
        else:
            cur.execute("SELECT * FROM sensor_status")
            result = cur.fetchall()

        cur.close()
        conn.close()
        return jsonify({"code": 200, "data": result})
    except Exception as e:
        logger.error(f"查询传感器状态失败：{str(e)}")
        return jsonify({"code": 500, "msg": f"查询传感器状态失败：{str(e)}"})


# ========== 3. 定时任务：自动标记离线传感器 ==========
def check_sensor_online():
    try:
        one_min_ago = datetime.datetime.now() - datetime.timedelta(minutes=1)
        conn = pymysql.connect(**DB_CONFIG)
        cur = conn.cursor()
        # 标记超过1分钟无心跳的传感器为离线
        cur.execute(
            "UPDATE sensor_status SET online_status=0 "
            "WHERE last_heartbeat_time < %s",
            (one_min_ago,)
        )
        conn.commit()
        cur.close()
        conn.close()
        logger.info("定时检查传感器状态：已更新离线传感器标记")
    except Exception as e:
        logger.error(f"定时检查传感器状态失败：{str(e)}")

# -------------------------- GPS 定位接口 --------------------------
# 1. GPS 设备上报位置接口
@app.route('/api/gps/report', methods=['POST'])
@handle_api_exceptions
@require_api_key  # 复用你现有的 API 密钥校验
def report_gps():
    data = request.get_json()
    device_id = data.get('device_id')
    lon = data.get('lon')
    lat = data.get('lat')
    speed = data.get('speed', 0)
    direction = data.get('direction', 0)
    locate_time_str = data.get('locate_time')

    if not device_id or lon is None or lat is None:
        return jsonify({"code": 400, "msg": "device_id、lon、lat 不能为空"}), 400

    # 解析定位时间
    if locate_time_str:
        locate_time = datetime.datetime.strptime(locate_time_str, '%Y-%m-%d %H:%M:%S')
    else:
        locate_time = datetime.datetime.now()

    # 保存到数据库
    gps_data = GPSData(
        device_id=device_id,
        lon=lon,
        lat=lat,
        speed=speed,
        direction=direction,
        locate_time=locate_time
    )
    db.session.add(gps_data)
    db.session.commit()

    logger.info(f"GPS上报成功: device={device_id}, lon={lon}, lat={lat}")
    return jsonify({"code": 200, "msg": "GPS上报成功"})

# 2. 查询设备最新位置接口
@app.route('/api/gps/latest', methods=['GET'])
@handle_api_exceptions
def get_latest_gps():
    device_id = request.args.get('device_id')
    if not device_id:
        return jsonify({"code": 400, "msg": "请传入 device_id"}), 400

    latest = GPSData.query.filter_by(device_id=device_id).order_by(GPSData.create_time.desc()).first()
    if not latest:
        return jsonify({"code": 404, "msg": "无GPS数据"}), 404

    return jsonify({
        "code": 200,
        "data": {
            "device_id": latest.device_id,
            "lon": latest.lon,
            "lat": latest.lat,
            "speed": latest.speed,
            "direction": latest.direction,
            "locate_time": latest.locate_time.strftime('%Y-%m-%d %H:%M:%S'),
            "create_time": latest.create_time.strftime('%Y-%m-%d %H:%M:%S')
        }
    })

# 3. 查询设备历史轨迹接口
@app.route('/api/gps/history', methods=['GET'])
@handle_api_exceptions
def get_gps_history():
    device_id = request.args.get('device_id')
    limit = int(request.args.get('limit', 50))  # 默认返回最近50条

    if not device_id:
        return jsonify({"code": 400, "msg": "请传入 device_id"}), 400

    history = GPSData.query.filter_by(device_id=device_id).order_by(GPSData.create_time.desc()).limit(limit).all()
    data = [{
        "lon": item.lon,
        "lat": item.lat,
        "speed": item.speed,
        "direction": item.direction,
        "locate_time": item.locate_time.strftime('%Y-%m-%d %H:%M:%S'),
        "create_time": item.create_time.strftime('%Y-%m-%d %H:%M:%S')
    } for item in history]

    return jsonify({"code": 200, "data": data})


# 配置 CORS，只允许前端的 Origin
CORS(app, resources=r'/*', origins="*")
# 6. 启动 Flask 服务（允许局域网访问）
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=5000, debug=True,threaded=True)