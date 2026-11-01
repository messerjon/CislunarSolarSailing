"""cislunar_sail -- mission simulator for distributed solar sails in cislunar space.

Modules
-------
constants    physical constants and Earth-Moon CR3BP units
backend      NumPy / PyTorch (GPU) array backend
sail         optical force model, materials, optimal steering, hybrid allocation
environment  Sun/Moon ephemerides, eclipses, NRLMSIS thermosphere tables
earth_orbit  orbit-averaged and Cowell Earth-centred spiral propagation
cr3bp        Earth-Moon CR3BP (+SRP, +solar gravity) dynamics, periodic orbits
"""
__version__ = "1.0.0"
