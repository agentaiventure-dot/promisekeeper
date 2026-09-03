FROM python:3.12-slim
WORKDIR /app
COPY promisekeeper ./promisekeeper
COPY fixtures ./fixtures
ENV HOST=0.0.0.0 PORT=7860 PROMISEKEEPER_PUBLIC=1 PROMISEKEEPER_DATA=/tmp/data
EXPOSE 7860
CMD ["python3", "-m", "promisekeeper"]
