package org.example.sdn;

import org.springframework.stereotype.Service;

@Service
public class PolicyService {
    private final PolicyRepository repository;
    private final ConstraintEvaluator evaluator;

    public PolicyService(
            PolicyRepository repository,
            ConstraintEvaluator evaluator) {
        this.repository = repository;
        this.evaluator = evaluator;
    }

    public DeploymentResult deploy(long id, PolicyDeployRequest request) {
        NetworkPolicy policy = repository.findPolicy(id);
        evaluator.evaluate(policy, request);
        repository.savePolicy(policy);
        return new DeploymentResult(policy.getId(), "READY");
    }
}
