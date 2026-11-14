FROM python:3.12-slim
WORKDIR /app
COPY index.html server.py ./
EXPOSE 8765
CMD ["python", "server.py"]
