ARG NODE_BASE
FROM ${NODE_BASE}
ARG OPENCODE_VERSION
LABEL io.coreeye.lab.runtime="opencode" io.coreeye.lab.opencode.version="${OPENCODE_VERSION}"
ENV HOME=/home/node XDG_CONFIG_HOME=/home/node/.config XDG_DATA_HOME=/home/node/.local/share XDG_CACHE_HOME=/home/node/.cache OPENCODE_CONFIG=/opt/lab/opencode.json
RUN mkdir -p /opt/opencode /opt/lab /workspace && chown node:node /opt/opencode /workspace
COPY opencode.json /opt/lab/opencode.json
USER node
WORKDIR /opt/opencode
RUN node -e 'const v=process.argv[1];if(!/^2\.\d+\.\d+$/.test(v)||Number(v.split(".")[1])===0&&Number(v.split(".")[2])<4)process.exit(1)' "$OPENCODE_VERSION" && npm install --prefix /opt/opencode --save-exact --no-audit --no-fund "@opencode/cli@$OPENCODE_VERSION" && test -x /opt/opencode/node_modules/.bin/opencode
WORKDIR /workspace
ENTRYPOINT ["/opt/opencode/node_modules/.bin/opencode"]
