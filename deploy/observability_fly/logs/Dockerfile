FROM grafana/loki:3.6.4@sha256:be31579ac047e9f78b81e48f3b69d3af709e7299b431d5aa78bcda43382f9511
COPY loki.yaml /etc/loki/config.yaml
CMD ["-config.file=/etc/loki/config.yaml"]
