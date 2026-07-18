FROM python:3.11-slim AS build
WORKDIR /src
RUN pip install --no-cache-dir poetry
COPY pyproject.toml ./
RUN poetry config virtualenvs.create false && poetry install --no-root --only main
COPY . .
RUN poetry install --no-root

FROM python:3.11-slim
WORKDIR /app
COPY --from=build /src /app
EXPOSE 8000
CMD ["uvicorn", "ai_eval_service.main:app", "--host", "0.0.0.0", "--port", "8000"]
