FROM python:3.13-slim-bookworm@sha256:a1165e272e578941b84abc79e4ab38a0305cd12803a5c4247979ac7655f4d641
WORKDIR /app
COPY integrations/analyst_foundry/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY integrations/analyst_foundry /app/integrations/analyst_foundry
ENV PYTHONUNBUFFERED=1 PORT=8088 OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=false
EXPOSE 8088
CMD ["python", "-m", "integrations.analyst_foundry.server"]
