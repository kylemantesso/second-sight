FROM odinlmshen/autoware-planning-control:v1.0

WORKDIR /opt/second-sight
COPY src/second_sight /opt/second-sight/src/second_sight
COPY components/latency_monitor/latency_monitor_node.py /opt/second-sight/latency_monitor_node.py

ENV PYTHONPATH=/opt/second-sight/src

CMD ["python3", "/opt/second-sight/latency_monitor_node.py"]
