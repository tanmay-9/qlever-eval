# The Java version the native CI path tests against. A JRE is enough:
# both the DataLoader and the server only run the jar.
FROM docker.io/eclipse-temurin:21-jre

RUN apt-get update && apt-get install -y wget \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt

# Download and set up Blazegraph
RUN wget https://github.com/blazegraph/database/releases/download/BLAZEGRAPH_2_1_6_RC/blazegraph.jar

# Set ownership to the user passed by UID and GID
ARG UID
ARG GID
RUN if [ "${UID:-}" != "" ] && [ "${GID:-}" != "" ]; then \
        chown -R ${UID}:${GID} /opt; \
    fi

RUN chmod u+x blazegraph.jar

CMD ["bash"]
