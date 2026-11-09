# Runtime-only image: run `mvn -DskipTests package` in minicc-cloud first.
FROM eclipse-temurin:21-jre-jammy

WORKDIR /app
COPY minicc-cloud/minicc-cloud-config/target/minicc-cloud-config-0.1.0.jar app.jar

EXPOSE 8888
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
