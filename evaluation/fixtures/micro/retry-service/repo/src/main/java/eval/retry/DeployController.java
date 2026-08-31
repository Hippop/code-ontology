package eval.retry;

public class DeployController {
    private final DeployService service;

    public DeployController(DeployService service) {
        this.service = service;
    }

    public String handle(String policy) {
        return service.deploy(policy);
    }
}
