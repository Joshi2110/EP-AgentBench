"""Reduced axial Hall-thruster electron transport and ion-energy diagnostic."""

from dataclasses import dataclass, fields
from math import cos, exp, isfinite, pi, sin, sqrt

from physics import ELEMENTARY_CHARGE, XENON_ION_MASS, cross_field_mobility


@dataclass(frozen=True)
class Parameters:
    voltage_v: float = 300.0
    length_m: float = 0.038
    n0_per_m3: float = 2.0e18
    te0_ev: float = 20.0
    b_peak_t: float = 0.02
    nu0_per_s: float = 2.0e7
    ion_inlet_m_per_s: float = 5000.0
    n_cells: int = 80
    density_bump: float = 0.25
    temperature_bump: float = 0.20
    nu_variation: float = 0.10


def _validate(p: Parameters) -> None:
    if isinstance(p.n_cells, bool) or not isinstance(p.n_cells, int) or p.n_cells < 4:
        raise ValueError("n_cells must be an integer of at least four")
    for field in fields(p):
        value = getattr(p, field.name)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
            raise ValueError(f"{field.name} must be a finite real number")
    if p.voltage_v < 0 or p.ion_inlet_m_per_s < 0:
        raise ValueError("Voltage and inlet speed must be nonnegative")
    if p.length_m <= 0 or p.n0_per_m3 <= 0 or p.te0_ev <= 0:
        raise ValueError("Length, density, and temperature must be positive")
    if p.nu0_per_s <= 0:
        raise ValueError("Collision frequency must be positive")
    if abs(p.density_bump) >= 1 or abs(p.temperature_bump) >= 1:
        raise ValueError("Profile variation must remain below unity")
    if abs(p.nu_variation) >= 1:
        raise ValueError("Collision profile must remain positive")


def sample_profiles(p: Parameters) -> dict[str, list[float]]:
    _validate(p)
    xi = [i / p.n_cells for i in range(p.n_cells + 1)]
    return {
        "x_m": [s * p.length_m for s in xi],
        "n_per_m3": [p.n0_per_m3 * (1 + p.density_bump * sin(pi * s)) for s in xi],
        "te_ev": [
            p.te0_ev * (1 + p.temperature_bump * sin(pi * s + 0.2)) for s in xi
        ],
        "b_t": [
            p.b_peak_t * (0.12 + 0.88 * exp(-((s - 0.76) / 0.24) ** 2))
            for s in xi
        ],
        "nu_per_s": [p.nu0_per_s * (1 + p.nu_variation * cos(pi * s)) for s in xi],
    }


def solve(p: Parameters) -> dict[str, object]:
    """Solve steady electron current and potential for prescribed plasma profiles.

    Conventions: +x points from anode to exit, phi(0)=Vd, phi(L)=0,
    E=-d(phi)/dx, positive j_e denotes conventional electron current.
    """
    data = sample_profiles(p)
    dx = p.length_m / p.n_cells
    n = data["n_per_m3"]
    te = data["te_ev"]
    b = data["b_t"]
    nu = data["nu_per_s"]
    pressure = [ELEMENTARY_CHARGE * ni * ti for ni, ti in zip(n, te)]

    faces = []
    for i in range(p.n_cells):
        nf = 0.5 * (n[i] + n[i + 1])
        bf = 0.5 * (b[i] + b[i + 1])
        nuf = 0.5 * (nu[i] + nu[i + 1])
        mu = cross_field_mobility(bf, nuf)
        gradp = (pressure[i + 1] - pressure[i]) / dx
        faces.append((nf, mu, gradp))

    resistive_integral = sum(
        dx / (ELEMENTARY_CHARGE * nf * mu) for nf, mu, _ in faces
    )
    pressure_integral = sum(
        dx * gradp / (ELEMENTARY_CHARGE * nf) for nf, _, gradp in faces
    )
    j_e = (p.voltage_v - pressure_integral) / resistive_integral
    e_face = [
        j_e / (ELEMENTARY_CHARGE * nf * mu) + gradp / (ELEMENTARY_CHARGE * nf)
        for nf, mu, gradp in faces
    ]

    phi = [p.voltage_v]
    for field in e_face:
        phi.append(phi[-1] - field * dx)

    ion_speed = []
    for potential in phi:
        speed_squared = p.ion_inlet_m_per_s**2 + (
            2 * ELEMENTARY_CHARGE * (p.voltage_v - potential) / XENON_ION_MASS
        )
        if speed_squared < 0:
            raise ValueError("Ion-energy diagnostic gives a negative speed squared")
        ion_speed.append(sqrt(speed_squared))

    return {
        **data,
        "pressure_pa": pressure,
        "mu_face_m2_per_vs": [mu for _, mu, _ in faces],
        "pressure_gradient_pa_per_m": [g for _, _, g in faces],
        "electric_field_v_per_m": e_face,
        "potential_v": phi,
        "electron_current_density_a_per_m2": j_e,
        "ion_speed_m_per_s": ion_speed,
    }
