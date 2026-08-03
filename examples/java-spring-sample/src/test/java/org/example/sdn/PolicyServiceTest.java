package org.example.sdn;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import org.junit.jupiter.api.Test;

class PolicyServiceTest {
    @Test
    void deploysPolicyAfterConstraintEvaluation() {
        PolicyRepository repository = mock(PolicyRepository.class);
        ConstraintEvaluator evaluator = mock(ConstraintEvaluator.class);
        NetworkPolicy policy = new NetworkPolicy();
        when(repository.findPolicy(42L)).thenReturn(policy);
        PolicyService service = new PolicyService(repository, evaluator);

        DeploymentResult result =
                service.deploy(42L, new PolicyDeployRequest(100));

        assertEquals("READY", result.status());
        verify(evaluator).evaluate(policy, new PolicyDeployRequest(100));
        verify(repository).savePolicy(policy);
    }
}
