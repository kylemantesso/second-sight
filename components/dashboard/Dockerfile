FROM odinlmshen/autoware-planning-control:v1.0

RUN curl --fail --silent --show-error --location \
      https://raw.githubusercontent.com/ros/rosdistro/master/ros.key | \
      gpg --batch --yes --dearmor \
        --output /usr/share/keyrings/ros2-latest-archive-keyring.gpg && \
    apt-get update && \
    apt-get install --yes --no-install-recommends ros-humble-foxglove-bridge && \
    rm -rf /var/lib/apt/lists/*

CMD ["ros2", "run", "foxglove_bridge", "foxglove_bridge", "--ros-args", \
    "-p", "port:=8765", "-p", "topic_whitelist:=['^/second_sight/.*']", \
    "-p", "service_whitelist:=['^$']", "-p", "param_whitelist:=['^$']", \
    "-p", "capabilities:=['clientPublish','connectionGraph']"]
