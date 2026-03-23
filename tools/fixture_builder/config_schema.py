"""Dataclass-based YAML configuration schema for the Fixture Builder CLI."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

import yaml


# ── Finish → Endcap Color mapping (global convention) ──────────────────
FINISH_TO_ENDCAP_COLOR = {
    "WH": "WH",
    "BK": "BK",
    "SV": "GR",  # Silver finish → Grey endcap
}

FINISH_NAMES = {
    "WH": "White",
    "BK": "Black",
    "SV": "Anodized Silver",
}

ENDCAP_COLOR_NAMES = {
    "WH": "White",
    "BK": "Black",
    "GR": "Grey",
}


@dataclass
class ProfileDef:
    """A single profile family definition (e.g., CA01 or CA02)."""
    family: str                          # e.g. "CA01"
    variant_label: str = ""              # e.g. "[WD]" — short shape label
    finishes: list[str] = field(default_factory=lambda: ["WH", "BK", "SV"])
    width_mm: float = 0.0
    height_mm: float = 0.0
    stock_length_mm: int = 2000
    max_assembled_length_mm: int = 2500
    is_cuttable: bool = True
    supports_joiners: bool = False
    joiner_system: str = ""              # e.g. "Eldorado-Single"
    lens_interface: str = "Snap-in"
    environment_ratings: list[str] = field(default_factory=lambda: ["Dry"])


@dataclass
class LensDef:
    """A lens family definition."""
    family: str                          # e.g. "CAXX" (shared) or "CH01" (specific)
    appearances: list[str] = field(default_factory=lambda: ["White"])
    shape: str = "WH"                    # shape segment in item code (WH, RD, etc.)
    stock_type: str = "Stick"
    stock_length_mm: int = 2000
    continuous_max_length_mm: int = 0


@dataclass
class AccessoryDef:
    """An accessory definition (mounting, joiner, or endcap)."""
    item_code: str                       # e.g. "ACC-CAXX-MC"
    accessory_type: str                  # "Mounting", "Joiner", or "Endcap"
    profile_family: str                  # e.g. "CAXX" or "CA01"
    mounting_method: str = ""            # e.g. "Mounting Clip"
    joiner_system: str = ""
    joiner_angle: str = ""
    endcap_style: str = ""
    allowance_override_per_side_mm: float = 0.0
    leader_cable: str = ""
    feed_type: str = ""
    qty_rule_type: str = "Per x mm"
    qty_rule_value: float = 304.8
    environment_rating: str = ""


@dataclass
class EndcapDef:
    """An endcap accessory definition — generated per profile family × color × style."""
    profile_family: str                  # e.g. "CA01"
    colors: list[str] = field(default_factory=lambda: ["WH", "BK", "GR"])
    styles: list[str] = field(default_factory=lambda: ["Solid", "Feed Through"])
    allowance_override_per_side_mm: float = 2.0

    def generate_items(self) -> list[AccessoryDef]:
        """Expand into individual AccessoryDef rows."""
        style_codes = {"Solid": "NO", "Feed Through": "HO"}
        results = []
        for color in self.colors:
            for style in self.styles:
                code = style_codes.get(style, style[:2].upper())
                item_code = f"EC-{self.profile_family}-{color}-{code}"
                results.append(AccessoryDef(
                    item_code=item_code,
                    accessory_type="Endcap",
                    profile_family=self.profile_family,
                    endcap_style=style,
                    allowance_override_per_side_mm=self.allowance_override_per_side_mm,
                    qty_rule_type="",
                    qty_rule_value=0,
                ))
        return results


@dataclass
class ProfileLensMapping:
    """Maps a set of profile families to lens families."""
    profile_families: list[str]          # e.g. ["CA01", "CA02"]
    lens_family: str                     # e.g. "CAXX"


@dataclass
class TemplateAllowedOptions:
    """Per-template allowed options, keyed by profile_family + led_package."""
    profile_family: str = ""
    led_package: str = ""
    allowed_finishes: list[str] = field(default_factory=list)
    allowed_lenses: list[str] = field(default_factory=list)
    allowed_mountings: list[str] = field(default_factory=list)
    allowed_endcap_styles: list[str] = field(default_factory=list)
    allowed_power_feed_types: list[str] = field(default_factory=list)
    allowed_environment_ratings: list[str] = field(default_factory=list)
    tape_offerings: list[str] = field(default_factory=list)
    base_price_msrp: float = 0.0
    price_per_ft_msrp: float = 0.0


@dataclass
class FixtureTemplateDef:
    """Definition for fixture templates (LED package variants).

    Global allowed_* fields serve as defaults when no per-template override exists.
    """
    led_packages: list[str] = field(default_factory=lambda: ["FS", "SW", "TW"])
    # Allowed options — global defaults, overridden by template_overrides
    allowed_finishes: list[str] = field(default_factory=list)
    allowed_lenses: list[str] = field(default_factory=list)
    allowed_mountings: list[str] = field(default_factory=list)
    allowed_endcap_styles: list[str] = field(default_factory=list)
    allowed_power_feed_types: list[str] = field(default_factory=list)
    allowed_environment_ratings: list[str] = field(default_factory=list)
    # Tape offerings (pre-existing references)
    tape_offerings: list[str] = field(default_factory=list)
    # Pricing
    base_price_msrp: float = 0.0
    price_per_ft_msrp: float = 0.0
    pricing_length_basis: str = "L_tape_cut"
    # Assembly
    assembled_max_len_mm: int = 2500
    leader_allowance_mm_per_fixture: int = 15
    default_profile_stock_len_mm: int = 2000


@dataclass
class DriverDef:
    """Driver eligibility definition."""
    driver_specs: list[str] = field(default_factory=lambda: ["PS-UNIV-24V-100W-IP66"])
    priority: int = 0


@dataclass
class SubmittalMappingDef:
    """Submittal mapping configuration."""
    clone_from_template: str = ""        # e.g. "ILL-AX01-FS"


@dataclass
class WebflowDef:
    """Webflow product skeleton configuration."""
    product_category: str = "linear-fixtures"
    sublabel: str = ""
    beam_angle: float = 110.0
    operating_temp_min_c: int = -40
    operating_temp_max_c: int = 60
    l70_life_hours: int = 50000
    warranty_years: int = 5
    # Configurator step order
    configurator_steps: list[str] = field(default_factory=lambda: [
        "Environment Rating",
        "CCT",
        "Lens Appearance",
        "Output Level",
        "Mounting Method",
        "Finish",
        "Length",
    ])


@dataclass
class FixtureBuilderConfig:
    """Top-level configuration for fixture builder."""
    # Mode
    mode: str = "new-family"             # "new-family" or "new-variant"

    # Series info
    series_name: str = ""                # e.g. "Castle"
    series_code: str = ""                # e.g. "CA" (used in template codes)

    # Supplier
    supplier: str = "Linea Lighting Co., Limited"
    brand: str = "ilLumenate Lighting"
    warranty_days: int = 1825            # 5 years

    # Profile definitions
    profiles: list[ProfileDef] = field(default_factory=list)

    # Lens definitions
    lenses: list[LensDef] = field(default_factory=list)

    # Profile → Lens mappings
    profile_lens_mappings: list[ProfileLensMapping] = field(default_factory=list)

    # Accessories
    accessories: list[AccessoryDef] = field(default_factory=list)
    endcaps: list[EndcapDef] = field(default_factory=list)

    # Fixture templates
    fixture_templates: FixtureTemplateDef = field(default_factory=FixtureTemplateDef)

    # Per-template allowed options overrides (keyed by profile_family + led_package)
    template_overrides: list[TemplateAllowedOptions] = field(default_factory=list)

    # Drivers
    drivers: DriverDef = field(default_factory=DriverDef)

    # Submittal mapping
    submittal_mapping: SubmittalMappingDef = field(default_factory=SubmittalMappingDef)

    # Webflow
    webflow: WebflowDef = field(default_factory=WebflowDef)

    def get_all_profile_families(self) -> list[str]:
        return [p.family for p in self.profiles]

    def get_template_codes(self) -> list[str]:
        """Return all fixture template codes: ILL-{family}-{led_pkg}."""
        codes = []
        for p in self.profiles:
            for pkg in self.fixture_templates.led_packages:
                codes.append(f"ILL-{p.family}-{pkg}")
        return codes

    def get_all_endcap_accessories(self) -> list[AccessoryDef]:
        """Expand endcap definitions into flat AccessoryDef list."""
        result = []
        for ec in self.endcaps:
            result.extend(ec.generate_items())
        return result

    def get_profile_variant_label(self, family: str) -> str:
        """Get variant label for a profile family, e.g. '[WD]'."""
        for p in self.profiles:
            if p.family == family:
                return p.variant_label
        return ""

    def get_options_for_template(self, profile_family: str, led_package: str) -> TemplateAllowedOptions:
        """Get allowed options for a specific template, falling back to global defaults."""
        for override in self.template_overrides:
            if override.profile_family == profile_family and override.led_package == led_package:
                return override
        ft = self.fixture_templates
        return TemplateAllowedOptions(
            profile_family=profile_family,
            led_package=led_package,
            allowed_finishes=ft.allowed_finishes,
            allowed_lenses=ft.allowed_lenses,
            allowed_mountings=ft.allowed_mountings,
            allowed_endcap_styles=ft.allowed_endcap_styles,
            allowed_power_feed_types=ft.allowed_power_feed_types,
            allowed_environment_ratings=ft.allowed_environment_ratings,
            tape_offerings=ft.tape_offerings,
            base_price_msrp=ft.base_price_msrp,
            price_per_ft_msrp=ft.price_per_ft_msrp,
        )


def _nested_dataclass(cls, data):
    """Recursively instantiate a dataclass from a dict."""
    if data is None:
        return cls()
    if not isinstance(data, dict):
        return data
    fieldtypes = {f.name: f.type for f in cls.__dataclass_fields__.values()}
    kwargs = {}
    for k, v in data.items():
        if k not in fieldtypes:
            continue
        ft = fieldtypes[k]
        # Handle list[SubDataclass]
        if isinstance(ft, str) and ft.startswith("list["):
            inner = ft[5:-1]
            inner_cls = _resolve_type(inner)
            if inner_cls and hasattr(inner_cls, "__dataclass_fields__"):
                kwargs[k] = [_nested_dataclass(inner_cls, item) for item in v]
            else:
                kwargs[k] = v
        elif isinstance(v, dict):
            inner_cls = _resolve_type(ft)
            if inner_cls and hasattr(inner_cls, "__dataclass_fields__"):
                kwargs[k] = _nested_dataclass(inner_cls, v)
            else:
                kwargs[k] = v
        else:
            kwargs[k] = v
    return cls(**kwargs)


def _resolve_type(type_str: str):
    """Resolve a type string to a class in this module."""
    import sys
    mod = sys.modules[__name__]
    # Strip Optional or other wrappers
    type_str = type_str.replace("Optional[", "").rstrip("]")
    return getattr(mod, type_str, None)


def load_config(path: str) -> FixtureBuilderConfig:
    """Load and validate a YAML configuration file."""
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if raw is None:
        raw = {}
    return _nested_dataclass(FixtureBuilderConfig, raw)


def save_config(config: FixtureBuilderConfig, path: str) -> None:
    """Save a config object to YAML."""
    import dataclasses
    data = dataclasses.asdict(config)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
