# Runtime-only image: run `mvn -DskipTests package` in minicc-cloud first.
FROM eclipse-temurin:21-jre-jammy

WORKDIR /app
COPY minicc-cloud/minicc-cloud-insights/target/minicc-cloud-insights-0.1.0.jar app.jar

# The Python engine owns both files; this image only ever opens them read-only.
ENV MINICC_STATE=/state

EXPOSE 8087
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
