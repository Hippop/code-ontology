package org.example.sdn;

import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/network-policies")
public class PolicyController {
    private final PolicyService service;

    public PolicyController(PolicyService service) {
        this.service = service;
    }

    @PostMapping("/{id}/deploy")
    public DeploymentResult deploy(
            @PathVariable long id,
            @RequestBody PolicyDeployRequest request) {
        return service.deploy(id, request);
    }
}
