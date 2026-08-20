"""Validated hydraulic-property inference for fractures and faults."""

from __future__ import annotations

from dataclasses import dataclass
import math


class HydraulicPropertyError(ValueError):
    """Raised when a fracture cannot be assigned consistent hydraulic properties."""


@dataclass(frozen=True)
class ResolvedHydraulicProperties:
    thickness: float
    porosity: float
    effective_aperture: float
    hydraulic_aperture: float
    transmissivity: float
    hydraulic_conductivity: float
    specific_storage: float
    provenance: dict[str, str]
    warnings: tuple[str, ...] = ()


def _positive(value, name: str, *, allow_zero: bool = False):
    if value is None:
        return None
    value = float(value)
    valid = value >= 0.0 if allow_zero else value > 0.0
    if not math.isfinite(value) or not valid:
        qualifier = "non-negative" if allow_zero else "positive"
        raise HydraulicPropertyError(f"{name} must be finite and {qualifier}")
    return value


def resolve_hydraulic_properties(
    source,
    *,
    density: float = 997.16,
    dynamic_viscosity: float = 8.9e-4,
    gravity: float = 9.80665,
    hydraulic_aperture_ratio: float = 1.0,
    discrepancy_tolerance: float = 1.0e-6,
) -> ResolvedHydraulicProperties:
    """Resolve one object's surface properties with explicit values taking precedence."""

    density = _positive(density, "density")
    dynamic_viscosity = _positive(dynamic_viscosity, "dynamic_viscosity")
    gravity = _positive(gravity, "gravity")
    ratio = _positive(hydraulic_aperture_ratio, "hydraulic_aperture_ratio")
    provenance: dict[str, str] = {}
    warnings: list[str] = []

    aperture = _positive(getattr(source, "aperture", None), "aperture")
    aperture_is_empirical = (
        hasattr(source, "_aperture")
        and getattr(source, "_aperture") is None
        and getattr(source, "aperture_constant", None) is not None
        and getattr(source, "size", None) is not None
        and aperture is not None
    )
    hydraulic_aperture = _positive(
        getattr(source, "hydraulic_aperture", None), "hydraulic_aperture"
    )
    effective = _positive(
        getattr(source, "effective_aperture", None), "effective_aperture"
    )
    porosity_value = getattr(source, "porosity", None)
    porosity = None if porosity_value is None else float(porosity_value)
    if porosity is not None and (not math.isfinite(porosity) or not 0.0 <= porosity <= 1.0):
        raise HydraulicPropertyError("porosity must lie in [0, 1]")

    explicit_t = _positive(getattr(source, "_transmissivity", None), "transmissivity", allow_zero=True)
    if explicit_t is None and not hasattr(source, "_transmissivity"):
        explicit_t = _positive(getattr(source, "transmissivity", None), "transmissivity", allow_zero=True)
    conductivity = _positive(
        getattr(source, "hydraulic_conductivity", None),
        "hydraulic_conductivity",
        allow_zero=True,
    )

    empirical_t = None
    coefficient = getattr(source, "transmissivity_constant", None)
    size = getattr(source, "size", None)
    if explicit_t is None and coefficient is not None and size is not None:
        radius_log = math.log10(float(size) / 2.0)
        empirical_t = _positive(
            float(coefficient) * radius_log * radius_log,
            "empirical transmissivity",
            allow_zero=True,
        )

    candidate_t = explicit_t if explicit_t is not None else empirical_t
    if aperture is None:
        if effective is not None:
            if porosity == 0.0:
                raise HydraulicPropertyError("positive effective aperture is incompatible with zero porosity")
            aperture = effective / (1.0 if porosity is None else porosity)
            provenance["thickness"] = "effective_aperture/porosity"
        elif hydraulic_aperture is not None:
            aperture = hydraulic_aperture
            provenance["thickness"] = "hydraulic_aperture"
        elif candidate_t is not None and candidate_t > 0.0:
            aperture = (12.0 * dynamic_viscosity * candidate_t / (density * gravity)) ** (1.0 / 3.0)
            provenance["thickness"] = "inverse_cubic_law"
        else:
            raise HydraulicPropertyError(
                "a physical, effective, or hydraulic aperture is required to upscale fracture volume"
            )
    else:
        provenance["thickness"] = "size_constitutive_law" if aperture_is_empirical else "mechanical_aperture"

    if porosity is None:
        if effective is not None:
            porosity = effective / aperture
            provenance["porosity"] = "effective_aperture/thickness"
        else:
            porosity = 1.0
            provenance["porosity"] = "default"
    if not 0.0 <= porosity <= 1.0 + discrepancy_tolerance:
        raise HydraulicPropertyError("effective aperture implies porosity outside [0, 1]")
    porosity = min(porosity, 1.0)
    resolved_effective = aperture * porosity
    if effective is not None and not math.isclose(
        effective, resolved_effective, rel_tol=discrepancy_tolerance, abs_tol=1.0e-15
    ):
        warnings.append("effective aperture disagrees with thickness times porosity")

    if hydraulic_aperture is None:
        hydraulic_aperture = aperture * ratio
        provenance["hydraulic_aperture"] = "mechanical_aperture_ratio"
    else:
        provenance["hydraulic_aperture"] = "explicit"
    cubic_t = density * gravity * hydraulic_aperture**3 / (12.0 * dynamic_viscosity)

    if explicit_t is not None:
        transmissivity = explicit_t
        provenance["transmissivity"] = "explicit"
    elif empirical_t is not None:
        transmissivity = empirical_t
        provenance["transmissivity"] = "size_constitutive_law"
    elif conductivity is not None:
        transmissivity = conductivity * aperture
        provenance["transmissivity"] = "hydraulic_conductivity*thickness"
    else:
        transmissivity = cubic_t
        provenance["transmissivity"] = "cubic_law"
    if (explicit_t is not None or empirical_t is not None) and not math.isclose(
        transmissivity, cubic_t, rel_tol=discrepancy_tolerance, abs_tol=1.0e-20
    ):
        warnings.append("selected transmissivity disagrees with cubic-law transmissivity")

    storage = getattr(source, "specific_storage", None)
    storage_origin = "explicit" if storage is not None else None
    if storage is None:
        storage = getattr(source, "_storativity", None)
        storage_origin = "explicit" if storage is not None else None
    if storage is None:
        coefficient = getattr(source, "storativity_constant", None)
        if coefficient is not None and size is not None:
            storage = float(coefficient) * math.log10(float(size) / 2.0)
            storage_origin = "size_constitutive_law"
    if storage is None and not hasattr(source, "_storativity"):
        storage = getattr(source, "storativity", None)
        storage_origin = "explicit" if storage is not None else None
    storage = 0.0 if storage is None else _positive(storage, "specific_storage", allow_zero=True)
    provenance["specific_storage"] = storage_origin or "default"

    return ResolvedHydraulicProperties(
        thickness=aperture,
        porosity=porosity,
        effective_aperture=resolved_effective,
        hydraulic_aperture=hydraulic_aperture,
        transmissivity=transmissivity,
        hydraulic_conductivity=transmissivity / aperture,
        specific_storage=storage,
        provenance=provenance,
        warnings=tuple(warnings),
    )
