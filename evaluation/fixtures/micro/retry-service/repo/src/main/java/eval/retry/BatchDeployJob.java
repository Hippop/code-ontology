package eval.retry;

public class BatchDeployJob {
    private final DeployService service;

    public BatchDeployJob(DeployService service) {
        this.service = service;
    }

    public String execute(String policy) {
        return service.deploy(policy);
    }
}
