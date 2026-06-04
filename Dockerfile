# No dependencies — the checker is Python standard library only.
FROM python:3.12-alpine
WORKDIR /app
COPY server.py .
EXPOSE 8000
CMD ["python", "server.py"]
