# syntax=docker/dockerfile:1
# The waveview site (ADR-0004): the web build of Surfer with the themes of Apparatica, and our page
# with the postMessage adapter around it. Versions live in versions.lock; docs/waveview.md.
# Build and test: `just waveview-build`, `just waveview-test`.

ARG RUST_IMAGE=rust:1.95-trixie@sha256:f49565f188ee00bc2a18dd418183f2c5f23ef7d6e691890517ed341a598f67c3
ARG RUNTIME_IMAGE=busybox:1.37@sha256:bdf57e528e45e4433820e045b29b4597825a1c9e38353532d90a01445013f82e

FROM ${RUST_IMAGE} AS surfer
COPY versions.lock /opt/waveview/versions.lock
# Trunk, wasm-bindgen and wasm-opt (binaryen) at the versions Surfer's CI gets, checked against the
# lock; trunk runs offline and would otherwise download the last two itself.
RUN . /opt/waveview/versions.lock \
    && rustup target add wasm32-unknown-unknown \
    && fetch() { curl -fsSL --retry 5 --retry-all-errors -o "$1" "$2" && echo "$3  $1" | sha256sum -c -; } \
    && fetch /tmp/trunk.tar.gz \
        "https://github.com/trunk-rs/trunk/releases/download/${TRUNK_VERSION}/trunk-x86_64-unknown-linux-gnu.tar.gz" \
        "${TRUNK_SHA256}" \
    && fetch /tmp/wasm-bindgen.tar.gz \
        "https://github.com/wasm-bindgen/wasm-bindgen/releases/download/${WASM_BINDGEN_VERSION}/wasm-bindgen-${WASM_BINDGEN_VERSION}-x86_64-unknown-linux-musl.tar.gz" \
        "${WASM_BINDGEN_SHA256}" \
    && fetch /tmp/binaryen.tar.gz \
        "https://github.com/WebAssembly/binaryen/releases/download/${BINARYEN_VERSION}/binaryen-${BINARYEN_VERSION}-x86_64-linux.tar.gz" \
        "${BINARYEN_SHA256}" \
    && tar -xzf /tmp/trunk.tar.gz -C /usr/local/bin trunk \
    && tar -xzf /tmp/wasm-bindgen.tar.gz -C /usr/local/bin --strip-components=1 \
        "wasm-bindgen-${WASM_BINDGEN_VERSION}-x86_64-unknown-linux-musl/wasm-bindgen" \
    && tar -xzf /tmp/binaryen.tar.gz -C /usr/local/bin --strip-components=2 \
        "binaryen-${BINARYEN_VERSION}/bin/wasm-opt" \
    && rm /tmp/*.tar.gz \
    && wasm-bindgen --version && wasm-opt --version
RUN . /opt/waveview/versions.lock \
    && git clone --depth 1 --branch "${SURFER_TAG}" --recurse-submodules --shallow-submodules \
        https://gitlab.com/surfer-project/surfer.git /src \
    && test "$(git -C /src rev-parse HEAD)" = "${SURFER_COMMIT}"
WORKDIR /src
# Crates of Cargo.lock up front: the build itself runs offline.
RUN cargo fetch --locked
# The only change to Surfer (EUPL-1.2, ADR-0012): our two themes join its built-in list, since a web
# build selects themes by name only (FR-WAV-04). The patch is these lines and themes/.
COPY themes/ /opt/waveview/themes/
RUN for theme in apparatica-light apparatica-dark; do \
        cp "/opt/waveview/themes/${theme}.toml" themes/ \
        && sed -i "s|^        theme!(\"dark+\"),|&\n        theme!(\"${theme}\"),|" libsurfer/src/config.rs \
        && grep -q "theme!(\"${theme}\")" libsurfer/src/config.rs; \
    done
# As Surfer's CI builds its web version (pages_build), with the accessibility tree.
RUN RUSTFLAGS="--cfg=web_sys_unstable_apis" trunk build --config=surfer/Trunk.toml index.html \
        --release --features accesskit --offline \
    && test -f surfer/dist/surfer.js && test -f surfer/dist/surfer_bg.wasm

# The site: our page and adapter next to Surfer's module and WASM, under the version path. Surfer's
# own page (analytics, service worker) is left out.
FROM ${RUST_IMAGE} AS site
COPY versions.lock /opt/waveview/versions.lock
COPY --from=surfer /src/surfer/dist/surfer.js /src/surfer/dist/surfer_bg.wasm /tmp/dist/
COPY --from=surfer /src/LICENSE-EUPL-1.2.txt /tmp/dist/
COPY site/ /tmp/dist/
RUN . /opt/waveview/versions.lock \
    && mkdir -p /out \
    && mv /tmp/dist "/out/${WAVEVIEW_VERSION}"

# The files alone, for the regression test: docker build --target export -o waveview/dist.
FROM scratch AS export
COPY --from=site /out/ /

# What the stand copies into the waveview bucket: /srv/waveview/<version>/.
FROM ${RUNTIME_IMAGE}
COPY --from=site /out/ /srv/waveview/
