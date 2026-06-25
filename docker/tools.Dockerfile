# osmium-tool + tippecanoe for the RMSP pipeline (Linux/arm64).
# OSRM and pmtiles use their own upstream multi-arch images.
FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        osmium-tool ca-certificates \
        git build-essential libsqlite3-dev zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# tippecanoe (maintained Felt fork) — provides tippecanoe + tile-join
RUN git clone --depth 1 https://github.com/felt/tippecanoe.git /tmp/tippecanoe \
    && make -C /tmp/tippecanoe -j"$(nproc)" \
    && make -C /tmp/tippecanoe install \
    && rm -rf /tmp/tippecanoe

WORKDIR /work
