package com.minicc.cloud.inspector;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.minicc.cloud.bridge.CapabilitiesClient;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.Locale;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

/**
 * {@code /api/capabilities} is the Python catalogue or a named failure, never a
 * guess.
 *
 * <p>The "Python" here is a stub script standing in for the interpreter, so the
 * test runs offline and without the minicc package installed. What is under test
 * is the contract: the endpoint echoes the payload it was given, and a child
 * that fails, dies, or prints garbage becomes a 503 whose reason says which.
 * If Java had its own tool list, the second payload below would not change the
 * answer - that is what these two cases are here to prevent.
 */
class CapabilityEndpointTest {

    private static final String PAYLOAD =
            "{\"count\":2,\"tools\":[{\"name\":\"alpha\",\"description\":\"first tool\"},"
                    + "{\"name\":\"beta\",\"description\":\"second tool\"}]}";

    @TempDir Path temp;

    @Test
    void theEndpointEchoesTheCatalogueTheChildPrinted() throws Exception {
        mvc(printStub(PAYLOAD)).perform(get("/api/capabilities"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.count").value(2))
                .andExpect(jsonPath("$.tools.length()").value(2))
                .andExpect(jsonPath("$.tools[0].name").value("alpha"))
                .andExpect(jsonPath("$.tools[1].name").value("beta"))
                .andExpect(jsonPath("$.tools[1].description").value("second tool"));
    }

    /** A different payload must produce a different answer; no Java-side list. */
    @Test
    void aDifferentPayloadIsWhatTheEndpointReturns() throws Exception {
        mvc(printStub("{\"count\":1,\"tools\":[{\"name\":\"only\",\"description\":\"\"}]}"))
                .perform(get("/api/capabilities"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.count").value(1))
                .andExpect(jsonPath("$.tools[0].name").value("only"));
    }

    @Test
    void outputThatIsNotJsonIsA503NamingThatFailure() throws Exception {
        mvc(printStub("this is not json")).perform(get("/api/capabilities"))
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.error").value("minicc-unavailable"))
                .andExpect(jsonPath("$.reason").value(org.hamcrest.Matchers.containsString(
                        "did not print JSON")))
                .andExpect(jsonPath("$.reason").value(org.hamcrest.Matchers.containsString("this is not json")));
    }

    /** A non-zero exit is a different sentence from unparseable output. */
    @Test
    void aFailedChildIsA503NamingTheExitRatherThanTheJson() throws Exception {
        Path stub = stub("@echo off\necho boom 1>&2\nexit /b 3",
                "echo boom >&2\nexit 3");
        mvc(stub).perform(get("/api/capabilities"))
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.error").value("minicc-unavailable"))
                .andExpect(jsonPath("$.reason").value(org.hamcrest.Matchers.containsString("exited 3")))
                .andExpect(jsonPath("$.reason").value(org.hamcrest.Matchers.not(
                        org.hamcrest.Matchers.containsString("did not print JSON"))));
    }

    private MockMvc mvc(Path python) {
        CapabilitiesClient client = new CapabilitiesClient(python, temp, Duration.ofSeconds(20));
        return MockMvcBuilders
                .standaloneSetup(new CapabilityController(new CapabilityService(client)))
                .setControllerAdvice(new BridgeFailureAdvice())
                .build();
    }

    /**
     * Writes one stub "interpreter". The bridge always prepends {@code -X utf8}
     * and the capability args; a shell script ignores them, which is exactly how
     * a fixed-answer stand-in behaves. A batch file is used on Windows because
     * the bridge starts the path directly, with no {@code cmd /c} of its own.
     */
    private Path stub(String windowsBody, String posixBody) throws IOException {
        boolean windows = System.getProperty("os.name", "").toLowerCase(Locale.ROOT).startsWith("windows");
        Path script = temp.resolve(windows ? "stub-python.cmd" : "stub-python.sh");
        if (windows) {
            Files.writeString(script, windowsBody + "\r\n", StandardCharsets.UTF_8);
        } else {
            Files.writeString(script, "#!/bin/sh\n" + posixBody + "\n", StandardCharsets.UTF_8);
            script.toFile().setExecutable(true);
        }
        return script;
    }

    /** A stub that prints one line to stdout and exits 0. */
    private Path printStub(String line) throws IOException {
        return stub("@echo off\necho " + line, "printf '%s\\n' '" + line + "'");
    }
}
