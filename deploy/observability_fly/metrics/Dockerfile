FROM prom/prometheus:v3.7.3@sha256:49214755b6153f90a597adcbff0252cc61069f8ab69ce8411285cd4a560e8038
COPY prometheus.yaml /etc/prometheus/prometheus.yml
CMD ["--config.file=/etc/prometheus/prometheus.yml", "--storage.tsdb.path=/prometheus", "--storage.tsdb.retention.time=48h", "--storage.tsdb.retention.size=512MB", "--web.enable-remote-write-receiver", "--web.listen-address=[::]:9090"]
