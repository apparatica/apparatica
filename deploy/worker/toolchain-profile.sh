#!/bin/sh
# Register the toolchain image of the stand as the default profile of SystemVerilog (docs/stand.md).
#
# Idempotent: run on every `docker compose up` by the `toolchain-profile` service. The tool versions
# come from the image itself (the `toolchain` service copies its versions.lock out), so the profile
# always describes the image it names.
# Environment: TOOLCHAIN_IMAGE, TOOLCHAIN_DIGEST, TOOLCHAIN_PROFILE_ID (default sv-<TOOLCHAIN_PROFILE>),
# NORMALIZATION_VERSION, WAVEVIEW_VERSION.
set -eu

versions=/opt/toolchain/versions.lock
profile=$(sed -n 's/^TOOLCHAIN_PROFILE=//p' "$versions")
exec apparatica-admin toolchain add "${TOOLCHAIN_PROFILE_ID:-sv-$profile}" \
	--image "$TOOLCHAIN_IMAGE" --digest "$TOOLCHAIN_DIGEST" --versions "$versions" \
	--normalization-version "$NORMALIZATION_VERSION" --waveview "$WAVEVIEW_VERSION" --default
