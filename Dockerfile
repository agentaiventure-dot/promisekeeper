FROM python:3.12-slim
WORKDIR /app
COPY promisekeeper ./promisekeeper
COPY fixtures ./fixtures
ENV HOST=0.0.0.0 PORT=8800 PROMISEKEEPER_PUBLIC=1 PROMISEKEEPER_DATA=/data
VOLUME ["/data"]
EXPOSE 8800
CMD ["python3", "-m", "promisekeeper"]
