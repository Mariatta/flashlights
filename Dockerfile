FROM python:3.14-bookworm AS base
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
RUN mkdir /code

WORKDIR /code

RUN pip --no-cache-dir --disable-pip-version-check install --upgrade pip setuptools wheel

COPY requirements-app.txt /code/
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements-app.txt

# ffmpeg brings ffprobe, which the media worker uses to measure videos and
# take thumbnail frames, and pulls the audio out for transcription.
RUN apt-get update && apt-get install -y gettext flite sox ffmpeg

# Two image flavours. Slim is the default: no transcription
# library, no model, about 500 MB lighter, what most instances need. Full
# adds machine transcription: build with --build-arg WHISPER_MODEL=small
# (or another faster-whisper model name) and the library goes in and the
# model is downloaded into /opt/whisper in this layer, before the code is
# copied, so a code-only build reuses it and the worker never downloads at
# run time. The engine itself is switched on by SPEAKER_TRANSCRIBE_ENGINE.
ARG WHISPER_MODEL=""
COPY requirements-media.txt /code/
RUN --mount=type=cache,target=/root/.cache/pip \
    if [ -n "$WHISPER_MODEL" ]; then \
        pip install -r requirements-media.txt && \
        python -c "from faster_whisper import download_model; download_model('$WHISPER_MODEL', '/opt/whisper/$WHISPER_MODEL')"; \
    fi


###############################################################################
#  Build our development container
###############################################################################
FROM base AS dev

ARG USER_ID
ARG GROUP_ID

RUN groupadd -o -g $GROUP_ID -r usergrp
RUN useradd -o -m -u $USER_ID -g $GROUP_ID user
RUN chown user /code

COPY requirements-dev.txt /code/
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements-dev.txt

RUN chown -R user /usr/local/lib/python3.14/site-packages

USER user
ENV PATH="${PATH}:/home/user/.local/bin"


###############################################################################
#  Build our production container
###############################################################################
FROM base

RUN  chown -R nobody /usr/local/lib/python3.14/site-packages

COPY . /code/

# collectstatic needs the settings, not the services: the boot contract's
# check is off for this one command, with placeholder values for the rest.
RUN \
    BOOT_CHECK=0 \
    SECRET_KEY=build-only \
    DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,[::1] \
    DATABASE_URL=postgres://localhost:5432/db \
    DJANGO_SETTINGS_MODULE=portal.settings \
    python manage.py collectstatic --noinput --clear

