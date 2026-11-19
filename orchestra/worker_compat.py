"""Versioned feature discovery on the existing Worker protocol envelope."""

WORKER_VERSION = "1.1.0"
GIT_CAPABILITIES = {"git_status": "git.status", "git_diff": "git.diff"}
KNOWN_CAPABILITIES = frozenset({"jobs", "files.read", "files.upload", *GIT_CAPABILITIES.values()})


def worker_manifest(protocol, *, upload=False):
    capabilities = KNOWN_CAPABILITIES if upload else KNOWN_CAPABILITIES - {"files.upload"}
    return {"version": WORKER_VERSION, "protocol": {"min": protocol, "max": protocol},
            "capabilities": sorted(capabilities)}


def negotiate_worker(info, protocol):
    """Treat old info replies as version 1. Modern metadata must be valid."""
    manifest = info.get("compatibility")
    if "compatibility" not in info:
        capabilities = {"jobs", "files.read"}
        if info.get("git_context") is True:
            capabilities.update(GIT_CAPABILITIES.values())
        if info.get("allow_upload") is True:
            capabilities.add("files.upload")
        return {"state": "legacy", "version": None, "min": protocol, "max": protocol,
                "capabilities": sorted(capabilities)}

    if not isinstance(manifest, dict):
        return {"state": "invalid", "capabilities": []}
    versions = manifest.get("protocol")
    capabilities = manifest.get("capabilities")
    version = manifest.get("version")
    if not (isinstance(versions, dict) and type(versions.get("min")) is int and type(versions.get("max")) is int
            and 0 < versions["min"] <= versions["max"] and isinstance(version, str) and 0 < len(version) <= 80
            and isinstance(capabilities, list) and len(capabilities) <= 100
            and all(isinstance(item, str) and len(item) <= 60 for item in capabilities)):
        return {"state": "invalid", "capabilities": []}
    compatible = versions["min"] <= protocol <= versions["max"]
    return {"state": "compatible" if compatible else "incompatible", "version": version,
            "min": versions["min"], "max": versions["max"],
            "capabilities": sorted(KNOWN_CAPABILITIES.intersection(capabilities)) if compatible else []}
