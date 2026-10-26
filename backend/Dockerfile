# The api image (also the ingestor and the one-shot setup services of deploy/compose.yaml).
# Build context: the repository root (judge is a path dependency of the backend).
ARG PYTHON_IMAGE=python:3.13-slim

FROM ${PYTHON_IMAGE} AS build
ARG POETRY_VERSION=2.3.2
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1 POETRY_NO_INTERACTION=1 \
    VIRTUAL_ENV=/opt/apparatica/venv POETRY_VIRTUALENVS_CREATE=false
RUN pip install "poetry==${POETRY_VERSION}" && python -m venv "$VIRTUAL_ENV"
ENV PATH=$VIRTUAL_ENV/bin:$PATH
WORKDIR /opt/apparatica
COPY judge/pyproject.toml judge/poetry.lock judge/poetry.toml judge/README.md judge/
COPY judge/src judge/src
COPY backend/pyproject.toml backend/poetry.lock backend/poetry.toml backend/README.md backend/
COPY backend/src backend/src
# Poetry installs into the active virtualenv at a fixed path, so the scripts get absolute shebangs.
RUN cd backend && poetry install --only main

FROM ${PYTHON_IMAGE}
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PATH=/opt/apparatica/venv/bin:$PATH \
    APX_CONFIG_DIR=/opt/apparatica/config
RUN useradd --system --uid 10001 --home-dir /opt/apparatica apparatica
WORKDIR /opt/apparatica
# The same paths as in the build stage: the virtualenv refers to them (judge is installed editable).
COPY --from=build /opt/apparatica /opt/apparatica
COPY config config
USER apparatica
EXPOSE 8000
# Only Caddy reaches the api in the compose network, so every peer may set X-Forwarded-*.
CMD ["apparatica", "serve", "--host", "0.0.0.0", "--port", "8000", "--forwarded-allow-ips", "*"]
