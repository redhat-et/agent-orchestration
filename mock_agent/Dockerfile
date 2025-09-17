FROM python:3.11-slim

WORKDIR /app

# Install uv for package management
RUN pip install uv

# Copy the agent files
COPY agent.py .
COPY data/ ./data/

# Install dependencies
RUN uv pip install --system "a2a-sdk[http-server]" uvicorn

# Expose the port
EXPOSE 10000

# Run the agent
CMD ["sh", "-c", "python agent.py --kb ./data/${AGENT_NAME}.txt --host 0.0.0.0 --port 10000"]
