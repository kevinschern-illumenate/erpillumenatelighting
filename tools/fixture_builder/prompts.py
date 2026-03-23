"""Interactive prompt functions for the Fixture Builder CLI.

When YAML config fields are missing, these functions collect input
from the user interactively via stdin.
"""

from __future__ import annotations

from .config_schema import (
    FixtureBuilderConfig,
    ProfileDef,
    LensDef,
    AccessoryDef,
    EndcapDef,
    ProfileLensMapping,
    FixtureTemplateDef,
    TemplateAllowedOptions,
    DriverDef,
    SubmittalMappingDef,
    WebflowDef,
)


def _input(prompt: str, default: str = "") -> str:
    """Prompt user with optional default."""
    if default:
        val = input(f"{prompt} [{default}]: ").strip()
        return val if val else default
    return input(f"{prompt}: ").strip()


def _input_int(prompt: str, default: int = 0) -> int:
    val = _input(prompt, str(default))
    return int(val) if val else default


def _input_float(prompt: str, default: float = 0.0) -> float:
    val = _input(prompt, str(default))
    return float(val) if val else default


def _input_bool(prompt: str, default: bool = True) -> bool:
    val = _input(prompt, "y" if default else "n")
    return val.lower() in ("y", "yes", "1", "true")


def _input_list(prompt: str, default: str = "") -> list[str]:
    """Prompt for a comma-separated list."""
    val = _input(f"{prompt} (comma-separated)", default)
    return [x.strip() for x in val.split(",") if x.strip()]


def prompt_series_info(config: FixtureBuilderConfig) -> None:
    """Prompt for series-level info if not in config."""
    if not config.series_name:
        config.series_name = _input("Series name (e.g., Castle)")
    if not config.series_code:
        config.series_code = _input("Series code prefix (e.g., CA)", config.series_name[:2].upper())


def prompt_profiles(config: FixtureBuilderConfig) -> None:
    """Prompt for profile definitions if empty."""
    if config.profiles:
        return

    print("\n── Profile Family Definitions ──")
    while True:
        family = _input("Profile family code (e.g., CA01, or blank to finish)")
        if not family:
            break

        label = _input("Variant label (e.g., [WD], [RC])", "")
        finishes = _input_list("Finishes", "WH,BK,SV")
        width = _input_float("Width (mm)")
        height = _input_float("Height (mm)")
        stock_len = _input_int("Stock length (mm)", 2000)
        max_len = _input_int("Max assembled length (mm)", 2500)
        cuttable = _input_bool("Is cuttable?", True)
        joiners = _input_bool("Supports joiners?", False)
        joiner_sys = ""
        if joiners:
            joiner_sys = _input("Joiner system", "")
        lens_iface = _input("Lens interface", "Snap-in")
        env_ratings = _input_list("Environment ratings", "Dry")

        config.profiles.append(ProfileDef(
            family=family, variant_label=label, finishes=finishes,
            width_mm=width, height_mm=height,
            stock_length_mm=stock_len, max_assembled_length_mm=max_len,
            is_cuttable=cuttable, supports_joiners=joiners,
            joiner_system=joiner_sys, lens_interface=lens_iface,
            environment_ratings=env_ratings,
        ))
        print(f"  Added profile {family}")


def prompt_lenses(config: FixtureBuilderConfig) -> None:
    """Prompt for lens definitions if empty."""
    if config.lenses:
        return

    print("\n── Lens Family Definitions ──")
    while True:
        family = _input("Lens family code (e.g., CAXX, CH01, or blank to finish)")
        if not family:
            break

        appearances = _input_list("Lens appearances", "White")
        shape = _input("Shape code for item code (e.g., WH, RD)", "WH")
        stock_type = _input("Stock type (Stick/Continuous Roll)", "Stick")
        stock_len = _input_int("Stock length (mm)", 2000)

        config.lenses.append(LensDef(
            family=family, appearances=appearances, shape=shape,
            stock_type=stock_type, stock_length_mm=stock_len,
        ))
        print(f"  Added lens family {family}")


def prompt_profile_lens_mappings(config: FixtureBuilderConfig) -> None:
    """Prompt for profile → lens mappings if empty."""
    if config.profile_lens_mappings:
        return

    print("\n── Profile → Lens Mappings ──")
    families = [p.family for p in config.profiles]
    lens_families = [l.family for l in config.lenses]
    print(f"  Available profiles: {', '.join(families)}")
    print(f"  Available lens families: {', '.join(lens_families)}")

    while True:
        pf = _input("Profile families (comma-separated, or blank to finish)")
        if not pf:
            break
        profile_fams = [x.strip() for x in pf.split(",")]
        lens_fam = _input("Maps to lens family")

        config.profile_lens_mappings.append(ProfileLensMapping(
            profile_families=profile_fams, lens_family=lens_fam,
        ))


def prompt_accessories(config: FixtureBuilderConfig) -> None:
    """Prompt for accessory definitions if empty."""
    if config.accessories:
        return

    print("\n── Accessory Definitions ──")
    print("  Types: Mounting, Joiner")

    while True:
        item_code = _input("Accessory item code (e.g., ACC-CAXX-MC, or blank to finish)")
        if not item_code:
            break

        acc_type = _input("Type (Mounting/Joiner)", "Mounting")
        pfamily = _input("Profile family", "")
        mounting = ""
        joiner_sys = ""
        joiner_angle = ""
        qty_rule_type = "Per x mm"
        qty_rule_value = 304.8

        if acc_type == "Mounting":
            mounting = _input("Mounting method", "Mounting Clip")
            qty_rule_type = _input("QTY rule type", "Per x mm")
            qty_rule_value = _input_float("QTY rule value (mm)", 304.8)
        elif acc_type == "Joiner":
            joiner_sys = _input("Joiner system (blank for generic)", "")
            joiner_angle = _input("Joiner angle (blank for generic)", "")
            qty_rule_type = "Per Joint"
            qty_rule_value = 1

        config.accessories.append(AccessoryDef(
            item_code=item_code, accessory_type=acc_type,
            profile_family=pfamily, mounting_method=mounting,
            joiner_system=joiner_sys, joiner_angle=joiner_angle,
            qty_rule_type=qty_rule_type, qty_rule_value=qty_rule_value,
        ))
        print(f"  Added accessory {item_code}")


def prompt_endcaps(config: FixtureBuilderConfig) -> None:
    """Prompt for endcap definitions per profile family if empty."""
    if config.endcaps:
        return

    print("\n── Endcap Definitions ──")
    for profile in config.profiles:
        add = _input_bool(f"Add endcaps for {profile.family}?", True)
        if add:
            colors = _input_list("Endcap colors (codes)", "WH,BK,GR")
            styles = _input_list("Endcap styles", "Solid,Feed Through")
            allowance = _input_float("Allowance override per side (mm)", 2.0)

            config.endcaps.append(EndcapDef(
                profile_family=profile.family,
                colors=colors, styles=styles,
                allowance_override_per_side_mm=allowance,
            ))


def prompt_fixture_templates(config: FixtureBuilderConfig) -> None:
    """Prompt for fixture template settings — per profile × LED package.

    First asks for global LED packages and assembly defaults,
    then loops per profile family × LED package asking for allowed options.
    If template_overrides are already populated, skip.
    """
    ft = config.fixture_templates

    # Ask for LED packages (global across all templates)
    if ft.led_packages == ["FS", "SW", "TW"]:
        print("\n── Fixture Template Settings ──")
        ft.led_packages = _input_list("LED packages", ",".join(ft.led_packages))

    # If overrides already populated (from YAML), skip interactive loop
    if config.template_overrides:
        return

    # If global allowed options are already populated (from YAML without overrides),
    # use them as defaults and skip interactive loop
    if ft.allowed_finishes and ft.allowed_lenses:
        return

    # Ask per profile × LED package
    print("\n── Per-Template Allowed Options ──")
    print("  For each profile × LED package, specify allowed options.")
    print('  Press Enter to accept defaults, or type "same" to reuse the previous answers.\n')

    prev_opts = None
    for profile in config.profiles:
        for led_pkg in ft.led_packages:
            template_code = f"ILL-{profile.family}-{led_pkg}"
            print(f"\n  ── {template_code} ({profile.variant_label or profile.family}, {led_pkg}) ──")

            if prev_opts is not None:
                reuse = _input("  Reuse previous answers? (y/n)", "y")
                if reuse.lower() in ("y", "yes"):
                    config.template_overrides.append(TemplateAllowedOptions(
                        profile_family=profile.family,
                        led_package=led_pkg,
                        allowed_finishes=list(prev_opts.allowed_finishes),
                        allowed_lenses=list(prev_opts.allowed_lenses),
                        allowed_mountings=list(prev_opts.allowed_mountings),
                        allowed_endcap_styles=list(prev_opts.allowed_endcap_styles),
                        allowed_power_feed_types=list(prev_opts.allowed_power_feed_types),
                        allowed_environment_ratings=list(prev_opts.allowed_environment_ratings),
                        tape_offerings=list(prev_opts.tape_offerings),
                        base_price_msrp=prev_opts.base_price_msrp,
                        price_per_ft_msrp=prev_opts.price_per_ft_msrp,
                    ))
                    print(f"    ✓ Copied from previous")
                    continue

            finishes = _input_list("Allowed finishes (names)", "White,Black,Anodized Silver")
            lenses = _input_list("Allowed lens appearances", "White")
            mountings = _input_list("Allowed mounting methods", "Mounting Clip")
            endcap_styles = _input_list("Allowed endcap styles", "Solid,Feed Through")
            power_feeds = _input_list("Allowed power feed types", "")
            env_ratings = _input_list("Allowed environment ratings", "Dry")
            tape_offs = _input_list("Tape offerings (item codes)", "")
            base_price = _input_float("Base price MSRP", 0.0)
            per_ft_price = _input_float("Price per ft MSRP", 0.0)

            opts = TemplateAllowedOptions(
                profile_family=profile.family,
                led_package=led_pkg,
                allowed_finishes=finishes,
                allowed_lenses=lenses,
                allowed_mountings=mountings,
                allowed_endcap_styles=endcap_styles,
                allowed_power_feed_types=power_feeds,
                allowed_environment_ratings=env_ratings,
                tape_offerings=tape_offs,
                base_price_msrp=base_price,
                price_per_ft_msrp=per_ft_price,
            )
            config.template_overrides.append(opts)
            prev_opts = opts
            print(f"    ✓ Added")


def prompt_drivers(config: FixtureBuilderConfig) -> None:
    """Prompt for driver eligibility if defaults."""
    if config.drivers.driver_specs == ["PS-UNIV-24V-100W-IP66"]:
        specs = _input_list("Driver specs", "PS-UNIV-24V-100W-IP66")
        config.drivers.driver_specs = specs


def prompt_submittal_mapping(config: FixtureBuilderConfig) -> None:
    """Prompt for submittal mapping config."""
    if not config.submittal_mapping.clone_from_template:
        config.submittal_mapping.clone_from_template = _input(
            "Clone submittal mappings from template (e.g., ILL-AX01-FS)", "ILL-AX01-FS"
        )


def prompt_all(config: FixtureBuilderConfig) -> None:
    """Run all interactive prompts for missing config."""
    prompt_series_info(config)

    if config.mode == "new-family":
        prompt_profiles(config)
        prompt_lenses(config)
        prompt_profile_lens_mappings(config)
        prompt_accessories(config)
        prompt_endcaps(config)

    prompt_fixture_templates(config)
    prompt_drivers(config)
    prompt_submittal_mapping(config)
