# Runtime-only image: run `mvn -DskipTests package` in minicc-cloud first.
#
# No pip install: `from minicc.changes import ChangeInspector` was measured to
# import and construct with openai, rich, tenacity, prompt_toolkit, httpx and
# anthropic all blocked at the meta-path finder. The change inspector is stdlib
# plus git, so the image carries python3 and git and nothing else.
FROM eclipse-temurin:21-jre-jammy

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/minicc
COPY minicc/ /opt/minicc/minicc/
COPY minicc-cloud/minicc-cloud-inspector/target/minicc-cloud-inspector-0.1.0.jar /app/app.jar

ENV MINICC_PYTHON=python3 \
    MINICC_REPO=/opt/minicc \
    MINICC_ALLOWEDROOTS=/workspaces \
    PYTHONUTF8=1 \
    PYTHONIOENCODING=utf-8 \
    LANG=C.UTF-8

# A mounted workspace belongs to the host's uid, so git refuses it as dubious
# ownership. These are environment overrides, not a written config file, and
# they name the mount rather than trusting every directory on the host.
ENV GIT_CONFIG_COUNT=1 \
    GIT_CONFIG_KEY_0=safe.directory \
    GIT_CONFIG_VALUE_0=/workspaces/target

EXPOSE 8081
ENTRYPOINT ["java", "-jar", "/app/app.jar"]