package com.minicc.cloud.evidence;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.http.HttpStatus;

/**
 * The only HTTP the evidence gate owns. Verdicts are facts plus timestamps:
 * {@code /api/evidence?latest=1} returns the freshest captured run,
 * {@code /api/evidence?run_id=…} returns (or backfills once) one specific run.
 */
@RestController
@RequestMapping("/api/evidence")
public class EvidenceController {

    private final EvidenceService service;

    public EvidenceController(EvidenceService service) {
        this.service = service;
    }

    @GetMapping
    public EvidenceResponse evidence(@RequestParam(required = false, name = "latest") String latest,
            @RequestParam(required = false, name = "run_id") String runId) {
        boolean wantsLatest = "1".equals(latest);
        if (wantsLatest && runId != null) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                    "give one of latest=1 or run_id=<digits>, not both");
        }
        if (wantsLatest) {
            return service.latest();
        }
        if (runId == null) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                    "give one of latest=1 or run_id=<digits>");
        }
        if (!runId.matches("^[0-9]{1,20}$")) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                    "run_id must be 1-20 digits, the GitHub run id");
        }
        return service.forRun(Long.parseLong(runId));
    }
}
