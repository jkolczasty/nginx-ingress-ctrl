FROM alpine:3.19

RUN apk update && apk upgrade && apk add docker-py py3-mako ca-certificates nginx && mkdir /etc/nginx/vhosts.d /config

COPY ingressd.py /ingress/
COPY templates/ /ingress/templates/

ENTRYPOINT python3 -u /ingress/ingressd.py
