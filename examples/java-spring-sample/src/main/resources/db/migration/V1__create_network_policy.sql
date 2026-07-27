CREATE TABLE network_policy (
    id BIGINT PRIMARY KEY,
    minimum_bandwidth_mbps INTEGER NOT NULL,
    status VARCHAR(32) NOT NULL
);
