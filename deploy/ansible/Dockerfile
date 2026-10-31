# The control node of deploy/ansible (docs/deployment.md): Ansible from poetry.lock, SSH and git, so
# that the playbooks run the same on Linux, macOS and Windows. `just provision` and `just deploy`
# start it with the repository at /repo and the SSH keys of the user at /ssh (read-only).
ARG PYTHON_IMAGE=python:3.13-slim

FROM ${PYTHON_IMAGE}
ARG POETRY_VERSION=2.3.2
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1 POETRY_NO_INTERACTION=1 \
    VIRTUAL_ENV=/opt/ansible POETRY_VIRTUALENVS_CREATE=false PYTHONDONTWRITEBYTECODE=1
RUN apt-get update \
    && apt-get install -y --no-install-recommends openssh-client git \
    && rm -rf /var/lib/apt/lists/* \
    && pip install "poetry==${POETRY_VERSION}" && python -m venv "$VIRTUAL_ENV"
ENV PATH=$VIRTUAL_ENV/bin:$PATH
COPY pyproject.toml poetry.lock /opt/ansible-project/
RUN cd /opt/ansible-project && poetry install --no-root
# The repository is mounted from the host: its owner differs from the user of the container.
RUN git config --system --add safe.directory '*'
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
# The mount from Windows is world-writable: Ansible reads a configuration there only when named.
ENV ANSIBLE_CONFIG=/repo/deploy/ansible/ansible.cfg
WORKDIR /repo/deploy/ansible
ENTRYPOINT ["sh", "/usr/local/bin/entrypoint.sh"]
CMD ["ansible-playbook", "--version"]
