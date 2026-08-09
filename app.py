"""Plane Radar public entry point."""
try:
    from .radar_base import PlaneRadarApp as _RadarBase
except ImportError:
    from radar_base import PlaneRadarApp as _RadarBase


class PlaneRadarApp(_RadarBase):
    pass


__app_export__ = PlaneRadarApp
