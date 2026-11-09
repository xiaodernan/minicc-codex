# Runtime-only image: run `mvn -DskipTests package` in minicc-cloud first.
FROM eclipse-temurin:21-jre-jammy

WORKDIR /app
COPY minicc-cloud/minicc-cloud-tasks/target/minicc-cloud-tasks-0.1.0.jar app.jar

# The Python engine owns the database; this image only opens it read-only.
ENV MINICC_STATE=/state

EXPOSE 8082
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
