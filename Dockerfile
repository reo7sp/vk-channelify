FROM python:3.14 AS builder

WORKDIR /usr/src/app

ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1

RUN pip install --no-cache-dir poetry

COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-root --no-ansi


FROM builder AS test

ENV PATH="/usr/src/app/.venv/bin:$PATH"

RUN poetry install --with dev --no-root --no-ansi

COPY . .

CMD ["pytest", "-q"]


FROM python:3.14-slim AS runtime

WORKDIR /usr/src/app

COPY --from=builder /usr/src/app/.venv ./.venv

COPY . .

EXPOSE 80
ENV PORT=80
ENV PYTHONPATH=/usr/src/app
ENV PATH="/usr/src/app/.venv/bin:$PATH"
CMD ["python", "app.py"]
