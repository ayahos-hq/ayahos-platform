FROM otel/opentelemetry-collector-contrib:0.144.0@sha256:213886eb6407af91b87fa47551c3632be1a6419ff3a5114ef1e6fc364628496f
COPY --chown=10001:10001 collector.yaml /etc/otelcol-contrib/config.yaml
CMD ["--config=/etc/otelcol-contrib/config.yaml"]
