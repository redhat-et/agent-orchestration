FROM python:3.13-slim

WORKDIR /app

# Install uv for package management
RUN pip install uv

# Copy the agent files
COPY agent.py .
COPY data/ ./data/
COPY configs/ ./configs/

# Install dependencies (add authlib, rfc8785 for signing/verification support)
RUN uv pip install --system "a2a-sdk[http-server]" uvicorn PyYAML authlib rfc8785

# Create non-root user and set ownership
RUN groupadd -g 1001 appgroup \
    && useradd -u 1001 -g 1001 -M -s /usr/sbin/nologin appuser \
    && chown -R 1001:1001 /app

# Avoid writing pyc files to read-only FS
ENV PYTHONDONTWRITEBYTECODE=1

# Expose the port
EXPOSE 10000

# Drop root
USER 1001:1001

# Run the agent
# If AGENT_NAME is set and ./data/${AGENT_NAME}.txt exists, pass --kb; otherwise use defaults
CMD ["sh", "-c", "KB_ARG=; if [ -n \"$AGENT_NAME\" ] && [ -f \"./data/${AGENT_NAME}.txt\" ]; then KB_ARG=\"--kb ./data/${AGENT_NAME}.txt\"; fi; exec python agent.py $KB_ARG --host 0.0.0.0 --port 10000"]
