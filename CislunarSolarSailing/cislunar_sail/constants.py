"""Physical constants (SI units unless noted)."""
import math

# Earth
MU_EARTH = 3.986004418e14        # m^3/s^2
R_EARTH = 6378.137e3             # m
J2_EARTH = 1.08262668e-3
OMEGA_EARTH = 7.2921159e-5       # rad/s

# Moon
MU_MOON = 4.9028e12              # m^3/s^2
R_MOON = 1737.4e3                # m
J2_MOON = 2.033e-4
D_EARTH_MOON = 384400e3          # m, mean distance
N_MOON = math.sqrt((MU_EARTH + MU_MOON) / D_EARTH_MOON**3)  # rad/s (CR3BP mean motion)
MOON_INC_ECLIPTIC = math.radians(5.145)
MOON_NODE_PERIOD = 18.61 * 365.25 * 86400.0                 # regression period, s
R_SOI_MOON = 66100e3             # m, Laplace sphere of influence

# Sun
MU_SUN = 1.32712440018e20
AU = 1.495978707e11
R_SUN = 6.957e8
SOLAR_PRESSURE_1AU = 4.56e-6     # N/m^2, = W/c for a perfect absorber at 1 AU
N_SUN = 2.0 * math.pi / (365.256363 * 86400.0)
OBLIQUITY = math.radians(23.4393)

G0 = 9.80665
DAY = 86400.0
YEAR = 365.25 * DAY

# Earth-Moon CR3BP normalisation
CR3BP_MU = MU_MOON / (MU_EARTH + MU_MOON)    # ~0.012150
LU = D_EARTH_MOON                             # length unit, m
TU = 1.0 / N_MOON                             # time unit, s (~4.34 days)
VU = LU / TU                                  # m/s
AU_ACC = LU / TU**2                           # acceleration unit, m/s^2 (~2.73 mm/s^2)
# Sun direction in the rotating frame rotates at the synodic rate (nondimensional)
OMEGA_SUN_SYNODIC = 1.0 - N_SUN / N_MOON
