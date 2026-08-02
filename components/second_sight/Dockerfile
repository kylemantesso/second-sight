FROM odinlmshen/autoware-planning-control:v1.0

RUN python3 -m pip install --no-cache-dir \
    joblib==1.5.3 \
    numpy==1.26.4 \
    scipy==1.15.3 \
    scikit-learn==1.7.2

WORKDIR /opt/second-sight
COPY src/second_sight /opt/second-sight/src/second_sight
COPY components/second_sight/second_sight_node.py /opt/second-sight/second_sight_node.py

ENV PYTHONPATH=/opt/second-sight/src

CMD ["python3", "/opt/second-sight/second_sight_node.py"]
