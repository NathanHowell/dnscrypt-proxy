FROM golang:1-alpine3.22@sha256:d9c983d2ac66c3f43208dfb6b092dd1296baa058766e3aa88a1b233adeb416c1 AS build

RUN apk add --no-cache curl tar
RUN mkdir -p /go/github.com/DNSCrypt/dnscrypt-proxy
RUN curl --silent -L https://github.com/DNSCrypt/dnscrypt-proxy/archive/2.1.15.tar.gz | tar -C /go/github.com/DNSCrypt/dnscrypt-proxy --strip-components=1 -xzvf -
WORKDIR /go/github.com/DNSCrypt/dnscrypt-proxy/dnscrypt-proxy
RUN go install -ldflags "-s -w"

FROM alpine:3.23@sha256:865b95f46d98cf867a156fe4a135ad3fe50d2056aa3f25ed31662dff6da4eb62
RUN apk add --no-cache bind-tools
COPY --from=build /go/bin/dnscrypt-proxy /usr/bin/
COPY dnscrypt-proxy.toml /etc/dnscrypt-proxy/dnscrypt-proxy.toml

ENTRYPOINT ["/usr/bin/dnscrypt-proxy"]
CMD ["-config", "/etc/dnscrypt-proxy/dnscrypt-proxy.toml"]

HEALTHCHECK CMD host -t A one.one.one.one || exit 1

