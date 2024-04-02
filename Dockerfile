FROM alpine:3.19

RUN apk update && apk upgrade && apk add docker-py py3-mako ca-certificates tzdata dumb-init nginx && mkdir /config /templates /etc/nginx/vhosts.d /etc/nginx/vhosts.d.custom /etc/nginx/http.d.custom \
    && echo 'include /etc/nginx/http.d.custom/*.conf ;'  >> /etc/nginx/http.d/custom-includes.conf \
    && echo 'include /etc/nginx/vhosts.d.custom/*.conf ;'  >> /etc/nginx/http.d/custom-includes.conf

COPY entrypoint.sh /entrypoint.sh
COPY ingressd.py /ingress/
COPY templates/ /ingress/templates/

ENTRYPOINT ["/usr/bin/dumb-init", "--"]
CMD ["sh", "/entrypoint.sh"]
