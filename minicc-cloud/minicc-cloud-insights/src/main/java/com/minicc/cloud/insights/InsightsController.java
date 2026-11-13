package com.minicc.cloud.insights;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/insights")
public class InsightsController {

    private final InsightsService service;
    private final DiskProbe disk;

    public InsightsController(InsightsService service, DiskProbe disk) {
        this.service = service;
        this.disk = disk;
    }

    @GetMapping("/summary")
    public SummaryResponse summary(@RequestParam(required = false) String workspace) {
        return service.summarize(workspace);
    }

    @GetMapping("/disk")
    public DiskProbe.DiskSummary disk() {
        return disk.probe();
    }
}
