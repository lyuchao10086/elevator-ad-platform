# cloud/Dockerfile
FROM golang:1.22-alpine AS builder

WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -o gateway ./cmd/gateway

FROM alpine:latest
RUN apk --no-cache add ca-certificates tzdata

WORKDIR /root/
COPY --from=builder /app/gateway .
COPY --from=builder /app/configs/config.yaml ./configs/

EXPOSE 8080 50051 9090
CMD ["./gateway", "--config", "./configs/config.yaml"]