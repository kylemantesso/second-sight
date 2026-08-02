FROM odinlmshen/autoware-planning-control:v1.0

RUN python3 -m pip install --no-cache-dir PyYAML==6.0.3

WORKDIR /opt/second-sight
COPY src/second_sight /opt/second-sight/src/second_sight
COPY components/fault_injector/fault_injector_node.py /opt/second-sight/fault_injector_node.py

ENV PYTHONPATH=/opt/second-sight/src

CMD ["python3", "/opt/second-sight/fault_injector_node.py"]
