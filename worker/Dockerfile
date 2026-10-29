# The worker image of deploy/compose.yaml: `apparatica-worker` and `apx-sandboxd` (ADR-0003).
# Build context: the repository root (judge is a path dependency of the worker).
ARG PYTHON_IMAGE=python:3.13-slim
# The docker CLI of apx-sandboxd, a static binary: the daemon is the host's, through its socket.
ARG DOCKER_CLI_IMAGE=docker:29-cli

FROM ${DOCKER_CLI_IMAGE} AS docker

FROM ${PYTHON_IMAGE} AS build
ARG POETRY_VERSION=2.3.2
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1 POETRY_NO_INTERACTION=1 \
    VIRTUAL_ENV=/opt/apparatica/venv POETRY_VIRTUALENVS_CREATE=false
RUN pip install "poetry==${POETRY_VERSION}" && python -m venv "$VIRTUAL_ENV"
ENV PATH=$VIRTUAL_ENV/bin:$PATH
WORKDIR /opt/apparatica
COPY judge/pyproject.toml judge/poetry.lock judge/poetry.toml judge/README.md judge/
COPY judge/src judge/src
COPY worker/pyproject.toml worker/poetry.lock worker/poetry.toml worker/README.md worker/
COPY worker/src worker/src
# Poetry installs into the active virtualenv at a fixed path, so the scripts get absolute shebangs.
RUN cd worker && poetry install --only main

FROM ${PYTHON_IMAGE}
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PATH=/opt/apparatica/venv/bin:$PATH \
    APX_RESOURCE_CLASSES=/opt/apparatica/config/resource-classes.yaml
# The orchestrator runs as `apparatica`; apx-sandboxd runs as root for the docker socket and gives
# the group `apparatica` its own socket (APX_SANDBOXD_SOCKET_GROUP).
RUN useradd --system --uid 10001 --user-group --home-dir /opt/apparatica apparatica \
    && install -d -o apparatica -g apparatica /var/cache/apparatica/packages \
    && install -d -g apparatica -m 0750 /run/apx-sandboxd
COPY --from=docker /usr/local/bin/docker /usr/local/bin/docker
WORKDIR /opt/apparatica
# The same paths as in the build stage: the virtualenv refers to them (judge is installed editable).
COPY --from=build /opt/apparatica /opt/apparatica
COPY config config
USER apparatica
CMD ["apparatica-worker"]
