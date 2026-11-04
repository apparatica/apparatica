# Postgres of the platform with WAL-G (docs/backups.md): continuous archive of WAL, daily full
# backups and the weekly restore check to an S3 bucket (NFR-REL-04). Debian, not Alpine: WAL-G is
# released for glibc only. The databases use the builtin locale provider, so the C library of the
# image does not change their collations.
ARG POSTGRES_BASE_IMAGE=postgres:17-trixie
FROM ${POSTGRES_BASE_IMAGE}

# The release binary of WAL-G for Postgres, checked against its digest on GitHub. WALG_URL: a mirror
# of the same file where GitHub is unreachable.
ARG WALG_VERSION=v3.0.9
ARG WALG_SHA256=8015836f246a978f27b31a2462eac7765312558ae5b11ac033322b555abf9e22
ARG WALG_URL=https://github.com/wal-g/wal-g/releases/download/${WALG_VERSION}/wal-g-pg-24.04-amd64
ADD --checksum=sha256:${WALG_SHA256} --chmod=755 ${WALG_URL} /usr/local/bin/wal-g

COPY --chmod=755 apx-backup /usr/local/bin/apx-backup
