FROM alpine:3.19

RUN apk update && apk upgrade && apk add docker-py py3-mako ca-certificates nginx && mkdir /config /templates /etc/nginx/vhosts.d /etc/nginx/vhosts.d.custom /etc/nginx/http.d.custom \
    && echo 'include /etc/nginx/http.d.custom/*.conf ;'  >> /etc/nginx/http.d/custom-includes.conf \
    && echo 'include /etc/nginx/vhosts.d.custom/*.conf ;'  >> /etc/nginx/http.d/custom-includes.conf

COPY ingressd.py /ingress/
COPY templates/ /ingress/templates/

ENTRYPOINT python3 -u /ingress/ingressd.py
