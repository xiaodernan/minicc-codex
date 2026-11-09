# Runtime-only image: run `mvn -DskipTests package` in minicc-cloud first.
FROM eclipse-temurin:21-jre-jammy

WORKDIR /app
COPY minicc-cloud/minicc-cloud-registry/target/minicc-cloud-registry-0.1.0.jar app.jar

EXPOSE 8761
ENTRYPOINT ["java", "-jar", "/app/app.jar"]