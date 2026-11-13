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
    private final FleetService fleet;

    public InsightsController(InsightsService service, DiskProbe disk, FleetService fleet) {
        this.service = service;
        this.disk = disk;
        this.fleet = fleet;
    }

    @GetMapping("/summary")
    public SummaryResponse summary(@RequestParam(required = false) String workspace) {
        return service.summarize(workspace);
    }

    @GetMapping("/disk")
    public DiskProbe.DiskSummary disk() {
        return disk.probe();
    }

    @GetMapping("/fleet")
    public FleetResponse fleet() {
        return fleet.fleet();
    }
}
