# Optional Dockerfile — primary deploy target is Railway via Railpack,
# but Smithery and self-hosters benefit from a simple container build.
FROM python:3.11-slim

WORKDIR /app

# Pinned-version install for reproducibility
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8080
EXPOSE 8080

CMD ["python", "-m", "start"]
