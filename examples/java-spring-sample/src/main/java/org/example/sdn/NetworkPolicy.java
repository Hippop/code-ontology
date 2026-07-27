package org.example.sdn;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "network_policy")
public class NetworkPolicy {
    @Id
    private long id;

    private int minimumBandwidthMbps;

    public long getId() {
        return id;
    }

    public int getMinimumBandwidthMbps() {
        return minimumBandwidthMbps;
    }
}
