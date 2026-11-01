"""Physical constants and Earth-Moon system parameters.

SI units unless the name says otherwise (``_KM`` = kilometres, ``_D`` = days).
Values follow IAU/IERS conventions and the references used in the study
(McInnes 1999; Heiligers et al. 2015; Wawrzyniak & Howell 2009).
"""
from math import pi, sqrt

# --- Radiation pressure -----------------------------------------------------
C_LIGHT = 299_792_458.0                  # m/s
SOLAR_FLUX_1AU = 1361.0                  # W/m^2, total solar irradiance (Kopp & Lean 2011)
P_SRP_1AU = SOLAR_FLUX_1AU / C_LIGHT     # 4.540e-6 N/m^2 (absorbing surface)
SIGMA_SB = 5.670374419e-8                # W/m^2/K^4
G0 = 9.80665                             # m/s^2 (Isp conversion)

# --- Bodies (km, km^3/s^2) --------------------------------------------------
AU_KM = 149_597_870.7
MU_SUN = 1.32712440018e11
MU_EARTH = 398_600.4418
MU_MOON = 4_902.800066
R_EARTH = 6_378.137
R_MOON = 1_737.4
J2_EARTH = 1.08262668e-3
OMEGA_EARTH = 7.2921159e-5               # rad/s
OBLIQUITY_DEG = 23.4393
MOON_INC_ECL_DEG = 5.145
D_EARTH_MOON = 384_400.0                 # mean Earth-Moon distance, km

# --- Time -------------------------------------------------------------------
DAY_S = 86_400.0
YEAR_D = 365.25
YEAR_S = YEAR_D * DAY_S
SIDEREAL_MONTH_D = 27.321661
SYNODIC_MONTH_D = 29.530589

# Solar gravitational acceleration at 1 AU (m/s^2), used for lightness number
G_SUN_1AU = MU_SUN / AU_KM ** 2 * 1e3    # 5.93e-3 m/s^2

# --- Earth-Moon circular restricted three-body problem (CR3BP) ----------------
MU_EM = MU_MOON / (MU_EARTH + MU_MOON)   # 0.012150585
L_EM_KM = D_EARTH_MOON                   # length unit
T_EM_S = sqrt(L_EM_KM ** 3 / (MU_EARTH + MU_MOON))   # time unit, 375 190 s = 4.342 d
V_EM_KMS = L_EM_KM / T_EM_S              # velocity unit, 1.0245 km/s
A_EM_MS2 = L_EM_KM * 1e3 / T_EM_S ** 2   # acceleration unit, 2.7307e-3 m/s^2
A_EM_MMS2 = A_EM_MS2 * 1e3               # 2.7307 mm/s^2
OMEGA_SUN_SYNODIC = 1.0 - T_EM_S * 2 * pi / (YEAR_S)  # Sun rate in rotating frame, 0.9253
MASS_SUN_ND = MU_SUN / (MU_EARTH + MU_MOON)           # 328 900.5
A_SUN_ND = AU_KM / L_EM_KM                            # 389.17
SYNODIC_MONTH_ND = 2 * pi / OMEGA_SUN_SYNODIC         # one synodic month in time units


def mm_s2_to_nd(a_mm_s2):
    """Convert an acceleration in mm/s^2 to Earth-Moon CR3BP units."""
    return a_mm_s2 / A_EM_MMS2


def nd_to_mm_s2(a_nd):
    return a_nd * A_EM_MMS2


def characteristic_acc_ideal(area_m2, mass_kg):
    """Ideal-sail characteristic acceleration (m/s^2) at 1 AU: 2 P A / m."""
    return 2.0 * P_SRP_1AU * area_m2 / mass_kg


def lightness_number(a_c_ms2):
    return a_c_ms2 / G_SUN_1AU
