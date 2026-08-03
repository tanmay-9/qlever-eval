from __future__ import annotations

# Blazegraph is EOL, so this last release is the only version there is.
# It is what the Dockerfile downloads and what web.xml was taken from.
BLAZEGRAPH_VERSION = "2.1.6-RC"

# Where `index` tells the user to get the jar; the same URL the Dockerfile
# downloads.
BLAZEGRAPH_JAR_URL = (
    "https://github.com/blazegraph/database/releases/download/"
    "BLAZEGRAPH_2_1_6_RC/blazegraph.jar"
)

# The jar inside the image, downloaded by the Dockerfile to its `WORKDIR`.
CONTAINER_JAR_PATH = "/opt/blazegraph.jar"

# The loader and journal settings `setup-config` copies out of this package,
# and the journal file that RWStore.properties points Blazegraph at.
PROPERTIES_FILE = "RWStore.properties"
JOURNAL_FILE = "blazegraph.jnl"
