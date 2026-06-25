FROM alpine:3.20

RUN apk add --no-cache git bash rsync openssh-client

COPY entrypoint.sh /entrypoint.sh
COPY gitignore.template /templates/.gitignore
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
