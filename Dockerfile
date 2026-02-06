FROM python:3.12

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY src/ ./src/
COPY .env .env

# 创建必要目录
RUN mkdir -p data logs

# 启动机器人
CMD ["python", "src/main.py"]
