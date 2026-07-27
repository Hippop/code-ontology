package org.example.sdn;

import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class PolicyRejectedListener {
    @KafkaListener(topics = "network-policy-rejected")
    public void onRejected(DeploymentResult result) {
        // Sample consumer boundary used by the deterministic graph extractor.
    }
}
