FROM python:3.11-slim

# 代理构建参数
ARG HTTP_PROXY
ARG HTTPS_PROXY
ENV HTTP_PROXY=$HTTP_PROXY
ENV HTTPS_PROXY=$HTTPS_PROXY

# 安装必要工具
RUN apt-get update && apt-get install -y \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# 安装 Deno
RUN curl -fsSL https://deno.land/install.sh | sh
ENV DENO_INSTALL="/root/.deno"
ENV PATH="$DENO_INSTALL/bin:$PATH"

# 清除代理（运行时不需要）
ENV HTTP_PROXY=""
ENV HTTPS_PROXY=""

# 安装 langchain-sandbox
RUN pip install langchain-sandbox

# 复制并安装项目依赖
COPY requirements.txt .
RUN pip install -r requirements.txt

WORKDIR /app

CMD ["python"]