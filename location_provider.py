"""Position-provider discovery for Tildagon Plane Radar.

Uses the public Position capability first, with a compatibility fallback for
older GPS hexpansion firmware that exposes ``position`` but does not yet
advertise the capability.
"""

POSITION_CAPABILITY = (
    "https://tildagon.badge.emfcamp.org/capabilities/registry/position/"
)


def normalise_position(position):
    """Return a validated ``(lat, lon)`` tuple, or ``None``."""
    if not isinstance(position, (tuple, list)) or len(position) < 2:
        return None
    try:
        lat = float(position[0])
        lon = float(position[1])
    except (TypeError, ValueError):
        return None
    if not -90.0 <= lat <= 90.0 or not -180.0 <= lon <= 180.0:
        return None
    return lat, lon


def _provider_position(provider):
    try:
        position = normalise_position(provider.position)
    except Exception:
        return None
    if position is None:
        return None
    name = provider.__class__.__name__
    return position[0], position[1], name


def get_best_position():
    """Return ``(lat, lon, provider_name)`` from a running provider, or None."""
    # Preferred/current interface: Tildagon Position capability.
    try:
        from system.capabilities.utils import get_running_apps_by_capability

        providers = get_running_apps_by_capability(POSITION_CAPABILITY)
        for provider in providers:
            result = _provider_position(provider)
            if result is not None:
                return result
    except Exception:
        pass

    # Compatibility with GPS EEPROM apps predating the capability registry.
    # This deliberately only considers active hexpansion apps and validates
    # the shape/range of their ``position`` property before using it.
    try:
        from system.hexpansion.app import _hexpansion_manager

        for provider in _hexpansion_manager.hexpansion_apps.values():
            if provider is None or not hasattr(provider, "position"):
                continue
            result = _provider_position(provider)
            if result is not None:
                return result
    except Exception:
        pass

    return None
