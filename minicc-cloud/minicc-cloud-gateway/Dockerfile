# Runtime-only image: run `mvn -DskipTests package` in minicc-cloud first.
FROM eclipse-temurin:21-jre-jammy

WORKDIR /app
COPY minicc-cloud/minicc-cloud-gateway/target/minicc-cloud-gateway-0.1.0.jar app.jar

EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]