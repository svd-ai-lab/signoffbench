FROM --platform=linux/amd64 python@sha256:aaf08c5490d52cd92bc27142a5215b1e47355a5eaf9adfad2a0fbc022d0b5490
ENV PYTHONPATH=/opt/python PATH=/opt/python/bin:$PATH PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY build-inputs/wheels /tmp/wheels
COPY build-inputs/requirements.lock /tmp/requirements.lock
RUN python -m pip install --no-index --no-deps --require-hashes --find-links=/tmp/wheels --target=/opt/python -r /tmp/requirements.lock && rm -rf /tmp/wheels /tmp/requirements.lock && echo /opt/python > /usr/local/lib/python3.13/site-packages/supplied-runtime.pth && python -m pip check
USER root
COPY work /tests/work
COPY assets /tests/assets
COPY grade.py test.sh *.json /tests/
RUN mkdir -p /public /app/submission && cp /tests/work/runtime/controller_process.py /tests/work/runtime/controller_interface.py /public/ && chmod 755 /public && chmod 444 /public/*.py && chmod -R go-rwx /tests && chmod 755 /tests/test.sh
WORKDIR /tests
ENTRYPOINT []
