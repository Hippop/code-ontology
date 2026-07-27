package org.example.sdn;

import org.junit.jupiter.api.Test;

class PolicyServiceTest {
    private PolicyService service;

    @Test
    void deploysPolicyAfterConstraintEvaluation() {
        service.deploy(42L, new PolicyDeployRequest(100));
    }
}
