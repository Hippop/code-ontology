package org.example.sdn;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

@Repository
public interface PolicyRepository extends JpaRepository<NetworkPolicy, Long> {
    NetworkPolicy findPolicy(long id);

    NetworkPolicy savePolicy(NetworkPolicy policy);
}
