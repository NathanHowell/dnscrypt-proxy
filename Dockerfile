FROM golang:1-alpine3.22@sha256:727cfc3c40be55cd1bc9a4a059406b28a059857e3be752aa9d09531e12c20c56 AS build

RUN apk add --no-cache curl tar
RUN mkdir -p /go/github.com/DNSCrypt/dnscrypt-proxy
RUN curl --silent -L https://github.com/DNSCrypt/dnscrypt-proxy/archive/2.1.16.tar.gz | tar -C /go/github.com/DNSCrypt/dnscrypt-proxy --strip-components=1 -xzvf -
WORKDIR /go/github.com/DNSCrypt/dnscrypt-proxy/dnscrypt-proxy
RUN go install -ldflags "-s -w"

FROM alpine:3.24@sha256:28bd5fe8b56d1bd048e5babf5b10710ebe0bae67db86916198a6eec434943f8b
RUN apk add --no-cache bind-tools
COPY --from=build /go/bin/dnscrypt-proxy /usr/bin/
COPY dnscrypt-proxy.toml /etc/dnscrypt-proxy/dnscrypt-proxy.toml

ENTRYPOINT ["/usr/bin/dnscrypt-proxy"]
CMD ["-config", "/etc/dnscrypt-proxy/dnscrypt-proxy.toml"]

HEALTHCHECK CMD host -t A one.one.one.one || exit 1

