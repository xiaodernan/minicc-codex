# Runtime-only image: run `mvn -DskipTests package` in minicc-cloud first.
FROM eclipse-temurin:21-jre-jammy

WORKDIR /app
COPY minicc-cloud/minicc-cloud-evidence/target/minicc-cloud-evidence-0.1.0.jar app.jar

# The evidence cache is the service's own; the Python engine and the task
# store are never mounted and never written.
ENV MINICC_EVIDENCE_STORE=/evidence/evidence.jsonl

EXPOSE 8088
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
