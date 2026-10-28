"""Independent health for the optional trading service."""


def component_health(settings):
    result = {}
    if settings.execution.enabled:
        from dao_vang.web.execution_api import status

        value = status(settings)
        result["execution"] = {
            "healthy": value["healthy"],
            "age_seconds": value["heartbeat_age_seconds"],
            "paused": value["pause"],
        }
    return result
