package eval.retry;

import org.junit.jupiter.api.Test;

public class DeployServiceTest {
    private final DeployService service = new DeployService();

    @Test
    void deploysPolicy() {
        service.deploy("policy");
    }
}
