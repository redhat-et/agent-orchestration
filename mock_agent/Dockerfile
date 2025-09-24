FROM python:3.11-slim

WORKDIR /app

# Install uv for package management
RUN pip install uv

# Copy the agent files
COPY agent.py .
COPY data/ ./data/
COPY configs/ ./configs/

# Install dependencies
RUN uv pip install --system "a2a-sdk[http-server]" uvicorn PyYAML

# Expose the port
EXPOSE 10000

# Run the agent
CMD ["python", "agent.py", "--host", "0.0.0.0", "--port", "10000"]
