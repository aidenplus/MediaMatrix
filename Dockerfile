FROM python:3.10-slim

# 支持 UID/GID 映射，避免 NFO 文件权限冲突
ARG PUID=1000
ARG PGID=1000

RUN groupadd -g ${PGID} mediamatrix \
    && useradd -u ${PUID} -g mediamatrix -s /bin/sh -m mediamatrix

WORKDIR /app

# 先复制依赖文件，利用 Docker 层缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 创建运行时目录
RUN mkdir -p logs config plugins media \
    && chown -R mediamatrix:mediamatrix /app

USER mediamatrix

EXPOSE 8000

CMD ["python", "main.py"]
