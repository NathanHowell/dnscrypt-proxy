FROM golang:1-alpine3.22@sha256:6104e2bbe9f6a07a009159692fe0df1a97b77f5b7409ad804b17d6916c635ae5 AS build

RUN apk add --no-cache curl tar
RUN mkdir -p /go/github.com/DNSCrypt/dnscrypt-proxy
RUN curl --silent -L https://github.com/DNSCrypt/dnscrypt-proxy/archive/2.1.14.tar.gz | tar -C /go/github.com/DNSCrypt/dnscrypt-proxy --strip-components=1 -xzvf -
WORKDIR /go/github.com/DNSCrypt/dnscrypt-proxy/dnscrypt-proxy
RUN go install -ldflags "-s -w"

FROM alpine:3.22@sha256:4bcff63911fcb4448bd4fdacec207030997caf25e9bea4045fa6c8c44de311d1
RUN apk add --no-cache bind-tools
COPY --from=build /go/bin/dnscrypt-proxy /usr/bin/
COPY dnscrypt-proxy.toml /etc/dnscrypt-proxy/dnscrypt-proxy.toml

ENTRYPOINT ["/usr/bin/dnscrypt-proxy"]
CMD ["-config", "/etc/dnscrypt-proxy/dnscrypt-proxy.toml"]

HEALTHCHECK CMD host -t A one.one.one.one || exit 1

