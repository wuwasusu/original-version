import logging
from logging.handlers import RotatingFileHandler

# 配置日志格式（包含时间、模块、级别、消息）
log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
formatter = logging.Formatter(log_format, datefmt="%Y-%m-%d %H:%M:%S")

# 创建日志器
logger = logging.getLogger("sensor_system")
logger.setLevel(logging.INFO)  # 全局日志级别，可根据需求调整

# 创建控制台处理器（输出到终端）
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# 创建文件处理器（输出到日志文件，按大小滚动）
file_handler = RotatingFileHandler(
    "sensor_system.log",
    maxBytes=10 * 1024 * 1024,  # 单个日志文件最大10MB
    backupCount=5,  # 最多保留5个备份文件
    encoding="utf-8"
)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)
logger.info("日志系统初始化完成")