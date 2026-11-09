package com.minicc.cloud.inspector;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/changes")
public class ChangeController {

    private final ChangeService service;

    public ChangeController(ChangeService service) {
        this.service = service;
    }

    @GetMapping
    public ChangeReport summary(@RequestParam String workspace) {
        return service.summary(workspace);
    }

    @GetMapping("/diff")
    public DiffReport diff(@RequestParam String workspace, @RequestParam String path) {
        return service.diff(workspace, path);
    }
}