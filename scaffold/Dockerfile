FROM python:3.11-slim
WORKDIR /app

# Create a non-root user
RUN adduser --disabled-password --gecos "" myuser

# Switch to the non-root user
USER myuser

# Set up environment variables - Start
ENV PATH="/home/myuser/.local/bin:$PATH"

ENV GOOGLE_GENAI_USE_ENTERPRISE=1
ENV GOOGLE_CLOUD_PROJECT=YOUR_GCP_PROJECT_ID
ENV GOOGLE_CLOUD_LOCATION=us-central1

# Set up environment variables - End

# Install ADK - Start
RUN pip install "google-adk[a2a]==2.3.0"
# Install ADK - End

# Copy agent - Start

# Set permission
COPY --chown=myuser:myuser "agents/ambient-expense-agent/" "/app/agents/ambient-expense-agent/"

# Copy agent - End

# Install Agent Deps - Start
RUN pip install -r "/app/agents/ambient-expense-agent/requirements.txt"
# Install Agent Deps - End

EXPOSE 8000

CMD adk api_server --port=8000 --host=0.0.0.0 --session_service_uri=memory:// --artifact_service_uri=memory:// "/app/agents"
