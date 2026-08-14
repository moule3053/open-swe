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
    claim = _document(documents, "PersistentVolumeClaim", "openswe-postgresql-data")
    stateful_set = _document(documents, "StatefulSet", "openswe-postgresql")

    assert claim["spec"]["storageClassName"] == "standard-rwo"
    assert claim["spec"]["resources"]["requests"]["storage"] == "20Gi"
    volume = stateful_set["spec"]["template"]["spec"]["volumes"][0]
    assert volume["persistentVolumeClaim"]["claimName"] == "openswe-postgresql-data"
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
