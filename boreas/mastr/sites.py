"""Weather grid points and regional capacity weights.

Seed values approximate the MaStR regional distribution of installed capacity
(GW, rounded). Refresh from the Marktstammdatenregister CSV export monthly:
https://www.marktstammdatenregister.de/MaStR/Datendownload — the structure
below (point, lat, lon, capacity per tech) is all the feature engine needs.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Site:
    id: str
    lat: float
    lon: float
    wind_onshore_gw: float = 0.0
    wind_offshore_gw: float = 0.0
    solar_gw: float = 0.0


SITES: list[Site] = [
    # --- North Sea offshore clusters ---
    Site("ns_borkum", 54.05, 6.55, wind_offshore_gw=3.5),
    Site("ns_helgoland", 54.35, 7.70, wind_offshore_gw=2.5),
    Site("ns_sylt", 55.05, 7.50, wind_offshore_gw=1.5),
    # --- Baltic offshore ---
    Site("bs_arkona", 54.78, 14.10, wind_offshore_gw=1.2),
    Site("bs_fehmarn", 54.55, 11.30, wind_offshore_gw=0.5),
    # --- Onshore wind belt: Schleswig-Holstein / Lower Saxony / MV ---
    Site("sh_husum", 54.48, 9.05, wind_onshore_gw=4.0, solar_gw=1.0),
    Site("sh_kiel", 54.32, 10.12, wind_onshore_gw=2.5, solar_gw=0.8),
    Site("ni_emden", 53.37, 7.21, wind_onshore_gw=3.5, solar_gw=1.0),
    Site("ni_cuxhaven", 53.87, 8.70, wind_onshore_gw=2.5, solar_gw=0.6),
    Site("ni_hannover", 52.37, 9.73, wind_onshore_gw=3.0, solar_gw=1.5),
    Site("mv_rostock", 54.09, 12.10, wind_onshore_gw=2.0, solar_gw=0.8),
    Site("mv_greifswald", 54.09, 13.38, wind_onshore_gw=1.5, solar_gw=0.6),
    # --- Brandenburg / Saxony-Anhalt / Saxony ---
    Site("bb_prignitz", 53.10, 12.00, wind_onshore_gw=2.5, solar_gw=1.0),
    Site("bb_cottbus", 51.76, 14.33, wind_onshore_gw=2.0, solar_gw=1.8),
    Site("st_magdeburg", 52.13, 11.62, wind_onshore_gw=3.0, solar_gw=1.2),
    Site("sn_leipzig", 51.34, 12.37, wind_onshore_gw=1.5, solar_gw=1.5),
    # --- NRW / Hesse / RLP ---
    Site("nw_paderborn", 51.72, 8.75, wind_onshore_gw=3.0, solar_gw=1.5),
    Site("nw_aachen", 50.78, 6.08, wind_onshore_gw=1.5, solar_gw=1.2),
    Site("he_kassel", 51.31, 9.49, wind_onshore_gw=1.5, solar_gw=1.2),
    Site("rp_eifel", 50.25, 6.80, wind_onshore_gw=2.0, solar_gw=1.0),
    # --- Bavaria / BW solar belts ---
    Site("by_muenchen", 48.14, 11.58, wind_onshore_gw=0.4, solar_gw=5.0),
    Site("by_nuernberg", 49.45, 11.08, wind_onshore_gw=0.6, solar_gw=4.0),
    Site("by_passau", 48.57, 13.45, wind_onshore_gw=0.2, solar_gw=3.0),
    Site("bw_stuttgart", 48.78, 9.18, wind_onshore_gw=0.5, solar_gw=3.5),
    Site("bw_freiburg", 47.99, 7.85, wind_onshore_gw=0.3, solar_gw=2.0),
]

TOTAL_WIND_ON = sum(s.wind_onshore_gw for s in SITES)
TOTAL_WIND_OFF = sum(s.wind_offshore_gw for s in SITES)
TOTAL_SOLAR = sum(s.solar_gw for s in SITES)
