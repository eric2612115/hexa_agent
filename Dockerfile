FROM python:3.11.0-alpine

# 安裝必要的套件，包括 bash
RUN apk --update --upgrade add \
    gcc musl-dev jpeg-dev zlib-dev libffi-dev cairo-dev pango-dev gdk-pixbuf-dev git bash

# 升級 pip 並安裝 poetry
RUN pip install --upgrade pip
RUN pip install poetry && \
    poetry config virtualenvs.create false && \
    poetry config system-git-client true

# # 建立專案目錄並設定 poetry
WORKDIR /app
# RUN poetry config virtualenvs.create false
# RUN poetry config virtualenvs.in-project true --local

# 複製 pyproject.toml, poetry.toml, AND poetry.lock (使用明確的路徑以提高清晰度)
COPY pyproject.toml /app/

# 安裝相依套件。如果你的 CMD 需要你的專案程式碼，就不需要 --no-root。
# Poetry 會自動使用基礎映像檔中的 Python 3.11。
RUN poetry install --no-cache

# 複製整個專案。
COPY . /app/

# 開放端口
EXPOSE 7788

# 直接使用 uvicorn。Poetry 會處理虛擬環境。
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7788"]