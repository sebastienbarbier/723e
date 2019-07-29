FROM python:3.7-alpine

WORKDIR /app

RUN adduser -D seven23
RUN chown seven23:seven23 /app

COPY --chown=seven23 . .

RUN \
 apk add --no-cache postgresql-libs libstdc++ && \
 apk add --no-cache --virtual .build-deps alpine-sdk postgresql-dev && \
 python -m pip install --upgrade pip --no-cache-dir && \
 python -m pip install -r requirements.txt --no-cache-dir && \
 apk --purge del .build-deps

USER seven23
EXPOSE 8000

ENTRYPOINT [ "/app/docker-entrypoint.sh" ]
