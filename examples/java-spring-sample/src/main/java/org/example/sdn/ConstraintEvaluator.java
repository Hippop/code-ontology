package org.example.sdn;

import java.time.Duration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class ConstraintEvaluator {
    @Value("${topology.bandwidth.max-age:PT30S}")
    private Duration bandwidthMaxAge;

    public void evaluate(NetworkPolicy policy, PolicyDeployRequest request) {
        if (request.minimumBandwidthMbps() < 0) {
            throw new IllegalArgumentException("minimum bandwidth must be positive");
        }
    }
}
