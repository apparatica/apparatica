# syntax=docker/dockerfile:1
# Sandbox toolchain image, profile 1: Verilator, Z3, pyslang, Verible, apx-run, apx_tb_pkg
# (ADR-0003, specs/07 §5).
# Tool versions live in versions.lock. Build and test: `just toolchain-build`, `just toolchain-test`.

ARG BASE_IMAGE=debian:trixie-slim@sha256:62bd423aeee912639ca8ee681c2b762cb3e25137e0a92b20be455898a9f034ad

FROM ${BASE_IMAGE} AS base
COPY versions.lock /opt/apx/versions.lock
# Debian packages come from the current trixie release. Their versions are recorded in versions.lock
# and checked by the smoke tests, so a rebuild that picks up a newer package fails until the lock and
# TOOLCHAIN_PROFILE are updated. The published image digest is what pins a profile.
# DEBIAN_MIRROR optionally replaces deb.debian.org (e.g. http://mirror.yandex.ru/debian) for slow networks.
ARG DEBIAN_MIRROR=
RUN printf 'Acquire::Retries "5";\n' > /etc/apt/apt.conf.d/80retries \
    && if [ -n "${DEBIAN_MIRROR}" ]; then \
        sed -i "s#http://deb.debian.org/debian#${DEBIAN_MIRROR}#g" /etc/apt/sources.list.d/debian.sources; \
    fi

FROM base AS verilator
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        autoconf bison ca-certificates curl flex g++ help2man libfl-dev make perl python3 zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*
RUN . /opt/apx/versions.lock \
    && curl -fsSL --retry 5 --retry-all-errors -o /tmp/verilator.tar.gz \
        "https://github.com/verilator/verilator/archive/refs/tags/v${VERILATOR_VERSION}.tar.gz" \
    && echo "${VERILATOR_SHA256}  /tmp/verilator.tar.gz" | sha256sum -c - \
    && mkdir /tmp/verilator && tar -xzf /tmp/verilator.tar.gz -C /tmp/verilator --strip-components=1 \
    && cd /tmp/verilator \
    && autoconf && ./configure --prefix=/opt/verilator \
    && make -j"$(nproc)" && make install \
    && rm /opt/verilator/bin/verilator_bin_dbg \
    && mkdir -p /opt/licenses/verilator && cp -r LICENSE LICENSES /opt/licenses/verilator/ \
    && rm -rf /tmp/verilator /tmp/verilator.tar.gz

FROM base AS verible
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*
RUN . /opt/apx/versions.lock \
    && curl -fsSL --retry 5 --retry-all-errors -o /tmp/verible.tar.gz \
        "https://github.com/chipsalliance/verible/releases/download/${VERIBLE_VERSION}/verible-${VERIBLE_VERSION}-linux-static-x86_64.tar.gz" \
    && echo "${VERIBLE_SHA256}  /tmp/verible.tar.gz" | sha256sum -c - \
    && mkdir /opt/verible && tar -xzf /tmp/verible.tar.gz -C /opt/verible --strip-components=1 \
    && chmod -R a+rX /opt/verible \
    && curl -fsSL --retry 5 --retry-all-errors -o /tmp/LICENSE \
        "https://raw.githubusercontent.com/chipsalliance/verible/${VERIBLE_VERSION}/LICENSE" \
    && echo "${VERIBLE_LICENSE_SHA256}  /tmp/LICENSE" | sha256sum -c - \
    && mkdir -p /opt/licenses/verible && mv /tmp/LICENSE /opt/licenses/verible/ \
    && rm /tmp/verible.tar.gz

FROM base AS python
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates python3 python3-venv \
    && rm -rf /var/lib/apt/lists/*
RUN . /opt/apx/versions.lock \
    && printf '%s\n' \
        "pyslang==${PYSLANG_VERSION} --hash=sha256:${PYSLANG_SHA256}" \
        "nanobind-backend==${NANOBIND_BACKEND_VERSION} --hash=sha256:${NANOBIND_BACKEND_SHA256}" \
        > /tmp/requirements.txt \
    && python3 -m venv /opt/apx/venv \
    && /opt/apx/venv/bin/pip install --no-cache-dir --only-binary=:all: --require-hashes \
        -r /tmp/requirements.txt \
    && /opt/apx/venv/bin/pip uninstall -y pip

FROM base
# The source label links the GHCR package to the repository (visibility and access follow it).
LABEL org.opencontainers.image.source="https://github.com/apparatica/apparatica" \
      org.opencontainers.image.description="Apparatica sandbox toolchain (see toolchain/versions.lock)"
RUN apt-get update \
    && apt-get install -y --no-install-recommends g++ liblz4-dev make perl python3 z3 zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*
COPY --from=verilator /opt/verilator /opt/verilator
COPY --from=verilator /opt/licenses /opt/licenses
COPY --from=verible /opt/verible /opt/verible
COPY --from=verible /opt/licenses /opt/licenses
COPY --from=python /opt/apx/venv /opt/apx/venv
COPY --chmod=0755 apx-run/apx_run.py /opt/apx/bin/apx-run
COPY --chmod=0755 apx-verilate/apx-verilate /opt/apx/bin/apx-verilate
ENV PATH=/opt/apx/bin:/opt/apx/venv/bin:/opt/verilator/bin:/opt/verible/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# Prebuilt Verilator runtime (ADR-0003): read-only in the image, linked by apx-verilate.
RUN --mount=type=bind,source=apx-verilate,target=/tmp/apx-verilate \
    sh /tmp/apx-verilate/build-runtime.sh

# Testbench library (specs/06 §3.2), compiled first by the sim stage. After the runtime: editing it
# does not rebuild the runtime layer.
RUN --mount=type=bind,source=sv,target=/tmp/sv \
    install -D -m 0644 /tmp/sv/apx_tb_pkg.sv /opt/apx/sv/apx_tb_pkg.sv

RUN useradd --uid 10001 --user-group --home-dir /work --no-create-home --shell /usr/sbin/nologin sandbox \
    && mkdir /work && chown sandbox:sandbox /work
USER sandbox
ENV HOME=/work
WORKDIR /work
