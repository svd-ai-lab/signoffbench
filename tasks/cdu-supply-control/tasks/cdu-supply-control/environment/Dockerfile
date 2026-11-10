FROM --platform=linux/amd64 python@sha256:aaf08c5490d52cd92bc27142a5215b1e47355a5eaf9adfad2a0fbc022d0b5490
ENV PYTHONPATH=/opt/python PATH=/opt/python/bin:$PATH PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY build-inputs/wheels /tmp/wheels
COPY build-inputs/requirements.lock /tmp/requirements.lock
RUN python -m pip install --no-index --no-deps --require-hashes --find-links=/tmp/wheels --target=/opt/python -r /tmp/requirements.lock && rm -rf /tmp/wheels /tmp/requirements.lock && echo /opt/python > /usr/local/lib/python3.13/site-packages/supplied-runtime.pth && python -m pip check
# Install the supplied, hash-verified package closure without a package repository.
# Configure Python pre-dependencies before installing the complete offline set.
COPY build-inputs/debs /tmp/debs
RUN cd /tmp/debs && sha256sum -c SHA256SUMS && dpkg --install /tmp/debs/libexpat1_*.deb /tmp/debs/libpython3.13-minimal_*.deb /tmp/debs/python3.13-minimal_*.deb && dpkg --install /tmp/debs/python3-minimal_*.deb && dpkg --install /tmp/debs/*.deb && test -z "$(dpkg --audit)" && rm -rf /tmp/debs /var/lib/apt/lists/*
COPY work /app
WORKDIR /app
ENTRYPOINT []
