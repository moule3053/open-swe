from pathlib import Path

import yaml

DEPLOY_DIR = Path(__file__).parents[2] / "deploy" / "k8s"


def _documents(name: str) -> list[dict]:
    with (DEPLOY_DIR / name).open(encoding="utf-8") as manifest:
        return [document for document in yaml.safe_load_all(manifest) if document]


def _document(documents: list[dict], kind: str, name: str) -> dict:
    return next(
        document
        for document in documents
        if document["kind"] == kind and document["metadata"]["name"] == name
    )


def test_postgresql_uses_gke_persistent_disk():
    documents = _documents("postgresql.yaml")
    claim = _document(documents, "PersistentVolumeClaim", "alephat-postgresql-data")
    stateful_set = _document(documents, "StatefulSet", "alephat-postgresql")

    assert claim["spec"]["storageClassName"] == "standard-rwo"
    assert claim["spec"]["resources"]["requests"]["storage"] == "20Gi"
    volume = stateful_set["spec"]["template"]["spec"]["volumes"][0]
    assert volume["persistentVolumeClaim"]["claimName"] == "alephat-postgresql-data"
    assert "emptyDir" not in volume


def test_nats_persists_jetstream_with_single_writer_rollouts():
    documents = _documents("nats.yaml")
    claim = _document(documents, "PersistentVolumeClaim", "nats-data")
    deployment = _document(documents, "Deployment", "nats")

    assert claim["spec"]["storageClassName"] == "standard-rwo"
    assert claim["spec"]["resources"]["requests"]["storage"] == "20Gi"
    assert deployment["spec"]["strategy"]["type"] == "Recreate"
    pod_spec = deployment["spec"]["template"]["spec"]
    volume = pod_spec["volumes"][0]
    assert volume["persistentVolumeClaim"]["claimName"] == "nats-data"
    container = pod_spec["containers"][0]
    assert "--jetstream" in container["args"]
    store_dir_index = container["args"].index("--store_dir")
    assert container["args"][store_dir_index + 1] == "/data/jetstream"
    assert container["volumeMounts"][0]["mountPath"] == "/data"


def test_litellm_postgresql_uses_gke_persistent_disk():
    with (DEPLOY_DIR / "litellm-values.yaml").open(encoding="utf-8") as values_file:
        values = yaml.safe_load(values_file)

    persistence = values["postgresql"]["primary"]["persistence"]
    assert persistence == {
        "enabled": True,
        "storageClass": "standard-rwo",
        "size": "20Gi",
    }


def test_standalone_defaults_are_synced_to_the_seeded_org():
    config_map = _document(_documents("configmap.yaml"), "ConfigMap", "alephat-config")

    assert config_map["data"]["DEFAULT_SANDBOX_PROVIDER"] == "agent_sandbox"
    assert config_map["data"]["BOOTSTRAP_DEV_DEFAULTS"] == "true"

    workload_documents = {
        "api-deployment.yaml": ("Deployment", "alephat-api"),
        "harness-deployment.yaml": ("Deployment", "alephat-harness"),
        "webhook-deployment.yaml": ("Deployment", "alephat-webhook"),
        "migration-job.yaml": ("Job", "alephat-migrate"),
    }
    for manifest, (kind, name) in workload_documents.items():
        workload = _document(_documents(manifest), kind, name)
        pod_spec = workload["spec"]["template"]["spec"]
        migration_container = (pod_spec.get("initContainers") or pod_spec["containers"])[0]
        assert migration_container["envFrom"] == [{"configMapRef": {"name": "alephat-config"}}]


def test_agent_sandbox_uses_git_enabled_runtime_image():
    template = _document(
        _documents("agent-sandbox-template.yaml"), "SandboxTemplate", "python-runtime-template"
    )
    container = template["spec"]["podTemplate"]["spec"]["containers"][0]
    dockerfile = (DEPLOY_DIR.parent / "Dockerfile.sandbox").read_text(encoding="utf-8")

    assert container["image"].endswith("/alephat/alephat-sandbox:latest")
    assert "python-runtime-sandbox:v0.1.0" in dockerfile
    assert "ca-certificates curl gh git" in dockerfile
    assert "COPY deploy/sandbox-gh /usr/local/bin/gh" in dockerfile
