"""Quasi-one-dimensional ion momentum with mass addition from ionization."""

from dataclasses import dataclass, fields
from math import exp, isfinite

from physics import ELEMENTARY_CHARGE, XENON_ION_MASS, bohm_speed


@dataclass(frozen=True)
class Parameters:
    length_m: float = 0.025
    n_cells: int = 80
    e_peak_v_per_m: float = 30000.0
    field_center: float = 0.70
    field_width: float = 0.25
    s0_per_m3_s: float = 4e23
    source_center: float = 0.15
    source_width: float = 0.25
    n_inlet_per_m3: float = 5e17
    te_ev: float = 5.0
    u_neutral_m_per_s: float = 300.0


def _validate(p: Parameters) -> None:
    if isinstance(p.n_cells, bool) or not isinstance(p.n_cells, int) or p.n_cells < 4:
        raise ValueError("n_cells must be an integer of at least four")
    for field in fields(p):
        if field.name == "n_cells":
            continue
        value = getattr(p, field.name)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
            raise ValueError(f"{field.name} must be a finite real number")
    if p.length_m <= 0 or p.n_inlet_per_m3 <= 0 or p.te_ev <= 0:
        raise ValueError("Length, inlet density, and temperature must be positive")
    if p.field_width <= 0 or p.source_width <= 0:
        raise ValueError("Profile widths must be positive")
    if p.e_peak_v_per_m < 0 or p.s0_per_m3_s < 0 or p.u_neutral_m_per_s < 0:
        raise ValueError("Field, source, and neutral speed must be nonnegative")


def sample_profiles(p: Parameters) -> dict[str, list[float]]:
    """Prescribed field and ionization source at cell centres."""
    _validate(p)
    dx = p.length_m / p.n_cells
    centres = [(i + 0.5) / p.n_cells for i in range(p.n_cells)]
    return {
        "x_m": [i * dx for i in range(p.n_cells + 1)],
        "e_field_v_per_m": [p.e_peak_v_per_m * exp(-((s - p.field_center) / p.field_width) ** 2) for s in centres],
        "source_per_m3_s": [p.s0_per_m3_s * exp(-((s - p.source_center) / p.source_width) ** 2) for s in centres],
    }


def solve(p: Parameters) -> dict[str, object]:
    """March the particle and momentum fluxes across the channel.

    The state is represented by the conservative fluxes ``n*u`` and
    ``n*u*u``.  This makes the mass added in a cell carry its prescribed
    neutral birth velocity in the momentum balance as required by the model.
    """
    prescribed = sample_profiles(p)
    dx = p.length_m / p.n_cells
    field, source = prescribed["e_field_v_per_m"], prescribed["source_per_m3_s"]
    charge_to_mass = ELEMENTARY_CHARGE / XENON_ION_MASS
    inlet_speed = bohm_speed(p.te_ev)
    particle_flux = p.n_inlet_per_m3 * inlet_speed
    momentum_flux = p.n_inlet_per_m3 * inlet_speed**2
    density = [p.n_inlet_per_m3]
    speed = [inlet_speed]
    for e_cell, s_cell in zip(field, source):
        # Use the upwind (left-node) density for both cell source terms.
        n_upwind = density[-1]
        particle_flux += dx * s_cell
        momentum_flux += dx * (
            charge_to_mass * n_upwind * e_cell + p.u_neutral_m_per_s * s_cell
        )
        u_next = momentum_flux / particle_flux
        if not isfinite(u_next) or u_next <= 0:
            raise ValueError("Ion velocity became nonpositive")
        speed.append(u_next)
        density.append(particle_flux / u_next)
    momentum = XENON_ION_MASS * (density[-1] * speed[-1] ** 2 - density[0] * speed[0] ** 2)
    force = sum(
        dx
        * (
            ELEMENTARY_CHARGE * density[i] * field[i]
            + XENON_ION_MASS * p.u_neutral_m_per_s * source[i]
        )
        for i in range(p.n_cells)
    )
    return {
        **prescribed,
        "n_per_m3": density,
        "u_i_m_per_s": speed,
        "thrust_momentum_n_per_m2": momentum,
        "thrust_force_n_per_m2": force,
    }
