FROM prom/prometheus:latest
COPY prometheus.yml /etc/prometheus/prometheus.yml
CMD ["--config.file=/etc/prometheus/prometheus.yaml","--storage.tsdb.retention.time=15d","--web.enable-lifecycle"]
