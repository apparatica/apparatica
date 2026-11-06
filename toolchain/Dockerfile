# syntax=docker/dockerfile:1
# Sandbox toolchain image (ADR-0003, specs/07 §5): Verilator, Z3, pyslang, Verible, apx-run, apx-init,
# apx_tb_pkg; Yosys with sv-elab, OpenSTA and the Nangate45 liberty for synthesis (ADR-0007).
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

# Downloads of prebuilt files.
FROM base AS fetch
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

FROM fetch AS verible
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

FROM base AS yosys
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bison ca-certificates cmake curl flex g++ libffi-dev libreadline-dev make pkg-config python3 \
        tcl-dev zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*
# The release archive has no .git: sv-elab's `slang_version` would print UNKNOWN, so the slang revision
# comes from the archive's .git_archival.txt and must be the one in versions.lock (pyslang's).
RUN . /opt/apx/versions.lock \
    && curl -fsSL --retry 5 --retry-all-errors -o /tmp/yosys.tar.gz \
        "https://github.com/YosysHQ/yosys/releases/download/v${YOSYS_VERSION}/yosys.tar.gz" \
    && echo "${YOSYS_SHA256}  /tmp/yosys.tar.gz" | sha256sum -c - \
    && mkdir /tmp/yosys && tar -xzf /tmp/yosys.tar.gz -C /tmp/yosys \
    && cd /tmp/yosys \
    && slang="$(sed -n 's/^node: //p' libs/slang/.git_archival.txt)" \
    && if [ "${slang}" != "${SLANG_COMMIT}" ]; then \
        echo "Yosys ${YOSYS_VERSION} carries slang ${slang}, versions.lock has ${SLANG_COMMIT}" >&2; exit 1; \
    fi \
    && cmake -B build -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/opt/yosys \
        -DYOSYS_ENABLE_UNIT_TESTS=OFF -DYOSYS_WITH_PYTHON=OFF \
        -DSLANG_REVISION="${SLANG_COMMIT}" -DYOSYS_SLANG_REVISION="yosys-${YOSYS_VERSION}" \
    && cmake --build build -j"$(nproc)" && cmake --install build --strip \
    && mkdir -p /opt/licenses/yosys \
    && find . \( -path '*/tests' -o -path '*/docs' -o -path ./.github \) -prune \
        -o -type f \( -iname 'license*' -o -iname 'copying*' -o -iname 'copyright*' -o -path '*/LICENSES/*' \) \
        -print0 | xargs -0 cp --parents -t /opt/licenses/yosys \
    && rm -rf /tmp/yosys /tmp/yosys.tar.gz

FROM base AS opensta
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        autoconf automake bison ca-certificates cmake curl flex g++ libeigen3-dev libfl-dev libtool make \
        swig tcl-dev zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*
RUN . /opt/apx/versions.lock \
    && curl -fsSL --retry 5 --retry-all-errors -o /tmp/cudd.tar.gz \
        "https://github.com/cuddorg/cudd/archive/refs/tags/cudd-${CUDD_VERSION}.tar.gz" \
    && echo "${CUDD_SHA256}  /tmp/cudd.tar.gz" | sha256sum -c - \
    && mkdir /tmp/cudd && tar -xzf /tmp/cudd.tar.gz -C /tmp/cudd --strip-components=1 \
    && cd /tmp/cudd && autoreconf -fi && ./configure --prefix=/opt/cudd \
    && make -j"$(nproc)" && make install \
    && mkdir -p /opt/licenses/cudd && cp LICENSE /opt/licenses/cudd/ \
    && rm -rf /tmp/cudd /tmp/cudd.tar.gz
# Only the sta binary goes into the image (CUDD is linked statically); Eigen is compiled in from
# the Debian headers, so its version and license go along (MPL-2.0, ADR-0012).
RUN . /opt/apx/versions.lock \
    && curl -fsSL --retry 5 --retry-all-errors -o /tmp/opensta.tar.gz \
        "https://github.com/parallaxsw/OpenSTA/archive/${OPENSTA_COMMIT}.tar.gz" \
    && echo "${OPENSTA_SHA256}  /tmp/opensta.tar.gz" | sha256sum -c - \
    && mkdir /tmp/opensta && tar -xzf /tmp/opensta.tar.gz -C /tmp/opensta --strip-components=1 \
    && cd /tmp/opensta \
    && cmake -B build -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/tmp/opensta-install \
        -DCUDD_DIR=/opt/cudd \
    && cmake --build build -j"$(nproc)" && cmake --install build --strip \
    && install -D -m 0755 /tmp/opensta-install/bin/sta /opt/opensta/bin/sta \
    && mkdir -p /opt/licenses/opensta /opt/licenses/eigen \
    && cp LICENSE* /opt/licenses/opensta/ \
    && cp /usr/share/doc/libeigen3-dev/copyright /opt/licenses/eigen/ \
    && dpkg-query -W -f '${Version}' libeigen3-dev > /opt/licenses/eigen/VERSION \
    && rm -rf /tmp/opensta /tmp/opensta.tar.gz /tmp/opensta-install

FROM fetch AS nangate45
RUN . /opt/apx/versions.lock \
    && src="https://raw.githubusercontent.com/The-OpenROAD-Project/OpenROAD-flow-scripts/${NANGATE45_ORFS_COMMIT}/flow/platforms/nangate45" \
    && mkdir -p /opt/pdk/nangate45 && cd /opt/pdk/nangate45 \
    && for file in lib/NangateOpenCellLibrary_typical.lib LICENSE README.md; do \
        curl -fsSL --retry 5 --retry-all-errors -o "$(basename "${file}")" "${src}/${file}" || exit 1; \
    done \
    && printf '%s  %s\n' \
        "${NANGATE45_LIB_SHA256}" NangateOpenCellLibrary_typical.lib \
        "${NANGATE45_LICENSE_SHA256}" LICENSE \
        "${NANGATE45_README_SHA256}" README.md \
        | sha256sum -c - \
    && chmod 0644 /opt/pdk/nangate45/*

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
# libffi8, libreadline8t64, libtcl8.6: run-time libraries of Yosys and OpenSTA.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        g++ libffi8 liblz4-dev libreadline8t64 libtcl8.6 make perl python3 z3 zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*
COPY --from=verilator /opt/verilator /opt/verilator
COPY --from=verilator /opt/licenses /opt/licenses
COPY --from=verible /opt/verible /opt/verible
COPY --from=verible /opt/licenses /opt/licenses
COPY --from=python /opt/apx/venv /opt/apx/venv
COPY --from=yosys /opt/yosys /opt/yosys
COPY --from=yosys /opt/licenses /opt/licenses
COPY --from=opensta /opt/opensta /opt/opensta
COPY --from=opensta /opt/licenses /opt/licenses
# Synthesis library (ADR-0007): LICENSE and README.md (version and source) lie next to the liberty.
COPY --from=nangate45 /opt/pdk /opt/pdk
COPY --chmod=0755 apx-run/apx_run.py /opt/apx/bin/apx-run
COPY --chmod=0755 apx-verilate/apx-verilate /opt/apx/bin/apx-verilate
ENV PATH=/opt/apx/bin:/opt/apx/venv/bin:/opt/verilator/bin:/opt/verible/bin:/opt/yosys/bin:/opt/opensta/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# Prebuilt Verilator runtime (ADR-0003): read-only in the image, linked by apx-verilate.
RUN --mount=type=bind,source=apx-verilate,target=/tmp/apx-verilate \
    sh /tmp/apx-verilate/build-runtime.sh

# Testbench library (specs/06 §3.2), compiled first by the sim stage. After the runtime: editing it
# does not rebuild the runtime layer.
RUN --mount=type=bind,source=sv,target=/tmp/sv \
    install -D -m 0644 /tmp/sv/apx_tb_pkg.sv /opt/apx/sv/apx_tb_pkg.sv

# PID 1 of the sandbox container (S6): reaps the processes killed between stages.
COPY --chmod=0755 apx-init/apx_init.py /opt/apx/bin/apx-init

# Where the sources of the programs in the image are (ADR-0012): versions from versions.lock, the
# Debian packages as installed.
RUN --mount=type=bind,source=SOURCES.md.in,target=/tmp/SOURCES.md.in \
    set -a && . /opt/apx/versions.lock && set +a \
    && sed -e "s|@TOOLCHAIN_PROFILE@|${TOOLCHAIN_PROFILE}|g" \
           -e "s|@VERILATOR_VERSION@|${VERILATOR_VERSION}|g" \
           -e "s|@VERILATOR_SHA256@|${VERILATOR_SHA256}|g" \
           -e "s|@VERIBLE_VERSION@|${VERIBLE_VERSION}|g" \
           -e "s|@PYSLANG_VERSION@|${PYSLANG_VERSION}|g" \
           -e "s|@YOSYS_VERSION@|${YOSYS_VERSION}|g" \
           -e "s|@YOSYS_SHA256@|${YOSYS_SHA256}|g" \
           -e "s|@SLANG_COMMIT@|${SLANG_COMMIT}|g" \
           -e "s|@OPENSTA_VERSION@|${OPENSTA_VERSION}|g" \
           -e "s|@OPENSTA_COMMIT@|${OPENSTA_COMMIT}|g" \
           -e "s|@CUDD_VERSION@|${CUDD_VERSION}|g" \
           -e "s|@EIGEN_VERSION@|$(cat /opt/licenses/eigen/VERSION)|g" \
           -e "s|@NANGATE45_ORFS_COMMIT@|${NANGATE45_ORFS_COMMIT}|g" \
           /tmp/SOURCES.md.in > /opt/licenses/SOURCES.md \
    && dpkg-query -W -f '| ${Package} | ${Version} |\n' >> /opt/licenses/SOURCES.md

RUN useradd --uid 10001 --user-group --home-dir /work --no-create-home --shell /usr/sbin/nologin sandbox \
    && mkdir /work && chown sandbox:sandbox /work
USER sandbox
ENV HOME=/work
WORKDIR /work
CMD ["apx-init"]
